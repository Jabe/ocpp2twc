from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16.enums import Action, RegistrationStatus, AuthorizationStatus
from ocpp.v16 import call_result
from datetime import datetime, timezone
import logging
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class ChargingSession:
    id_tag: str
    transaction_id: int
    meter_start: int
    start_time: datetime
    total_energy_start: float = 0.0  # Store total energy at session start
    session_energy: float = 0.0

class ChargePoint(cp):
    def __init__(self, id, connection, twc):
        super().__init__(id, connection)
        self.twc = twc
        self.transaction_id = None
        self.last_session: Optional[ChargingSession] = None  # Store only the last session
        self.twc.set_ocpp_connected(True)

    async def start(self):
        """Handle OCPP messages"""
        logging.info(f"Client {self.id} connected")
        try:
            await super().start()
        except Exception as e:
            logging.error(f"Error in OCPP message loop: {e}")
            raise
        finally:
            logging.info(f"Client {self.id} disconnected")
            self.twc.set_ocpp_connected(False)

    def get_current_time(self):
        return datetime.now(timezone.utc).isoformat()

    @on(Action.BootNotification)
    def on_boot_notification(self, charge_point_vendor: str, charge_point_model: str, **kwargs):
        return call_result.BootNotificationPayload(
            current_time=self.get_current_time(),
            interval=300,
            status=RegistrationStatus.accepted
        )

    @on(Action.Heartbeat)
    def on_heartbeat(self):
        return call_result.HeartbeatPayload(
            current_time=self.get_current_time()
        )

    @on(Action.StatusNotification)
    def on_status_notification(self, connector_id: int, error_code: str, status: str, **kwargs):
        """Process status updates from charge point"""
        logging.info(f"OCPP Status: connector={connector_id}, status={status}, error={error_code}, extra={kwargs}")
        
        if error_code != "NoError":
            self.twc.set_error(True)
        else:
            self.twc.set_error(False)
            if status == "Charging":
                self.twc.set_vehicle_connected(True)
            elif status == "SuspendedEVSE":
                # Car is connected but not charging (contactors open)
                self.twc.set_vehicle_connected(True)
                self.twc.vitals.evse_state = 2  # ready
                self.twc.vitals.contactor_closed = False
            elif status == "SuspendedEV":
                # Car requested charging stop
                self.twc.set_vehicle_connected(True)
                self.twc.vitals.evse_state = 2  # ready
                self.twc.vitals.contactor_closed = False
            else:
                self.twc.set_vehicle_connected(False)
            
        return call_result.StatusNotificationPayload()

    @on(Action.Authorize)
    def on_authorize(self, id_tag: str):
        """Log authorization requests but always accept"""
        logging.info(f"Authorization request from charge point: {id_tag}")
        return call_result.AuthorizePayload(
            id_tag_info={"status": AuthorizationStatus.accepted}
        )

    @on(Action.StartTransaction)
    def on_start_transaction(self, connector_id: int, id_tag: str, meter_start: int, timestamp: str, **kwargs):
        """Track start of charging session with session restoration"""
        try:
            timestamp_dt = datetime.fromisoformat(timestamp)
        except ValueError:
            timestamp_dt = datetime.now(timezone.utc)

        self.transaction_id = int(timestamp_dt.timestamp())

        # Store current total energy as start point
        total_energy_start = self.twc.vitals.total_energy_wh
        session_energy = 0.0

        # Check if we have a previous session with same ID
        if self.last_session and self.last_session.id_tag == id_tag:
            logging.info(f"Restoring previous session for {id_tag} with {self.last_session.session_energy}Wh")
            session_energy = self.last_session.session_energy

        self.last_session = ChargingSession(
            id_tag=id_tag,
            transaction_id=self.transaction_id,
            meter_start=meter_start,
            start_time=timestamp_dt,
            total_energy_start=total_energy_start,
            session_energy=session_energy
        )

        logging.info(f"Transaction started: id={self.transaction_id}, connector={connector_id}, "
                    f"id_tag={id_tag}, total_start={total_energy_start}Wh")

        return call_result.StartTransactionPayload(
            transaction_id=self.transaction_id,
            id_tag_info={"status": AuthorizationStatus.accepted}
        )

    @on(Action.StopTransaction)
    def on_stop_transaction(self, meter_stop: int, timestamp: str, transaction_id: int, **kwargs):
        """Store final session state"""
        if self.last_session:
            logging.info(f"Transaction stopped: id={transaction_id}, "
                        f"id_tag={self.last_session.id_tag}, "
                        f"energy={self.last_session.session_energy}Wh")
        self.transaction_id = None
        return call_result.StopTransactionPayload()

    @on(Action.MeterValues)
    def on_meter_values(self, connector_id: int, meter_value: list, **kwargs):
        if not meter_value:
            return call_result.MeterValuesPayload()

        try:
            for reading in meter_value:
                sampled_values = reading.get('sampled_value', [])
                timestamp = reading.get('timestamp')
                
                # Log raw meter values
                logging.debug(f"OCPP MeterValues: connector={connector_id}, timestamp={timestamp}")
                for sv in sampled_values:
                    measurand = sv.get('measurand', '')
                    value = sv.get('value', '0')
                    unit = sv.get('unit', '')
                    phase = sv.get('phase', '')
                    logging.debug(f"  {measurand}: {value} {unit} {f'(phase {phase})' if phase else ''}")
                
                currents = {'L1': 0, 'L2': 0, 'L3': 0, 'N': 0}
                voltages = {'L1': 0, 'L2': 0, 'L3': 0, 'N': 0}
                powers = {'L1': 0, 'L2': 0, 'L3': 0}  # Per-phase power
                frequency = 50.0
                session_energy = 0
                total_energy = 0
                temperature = 20.0  # Default temperature
                current_offered = 0
                power_offered = 0
                
                interval_energy_reported = False  # Flag to track if interval energy was reported
                
                # Process values
                for sv in sampled_values:
                    measurand = sv.get('measurand', '')
                    value = float(sv.get('value', '0'))
                    phase = sv.get('phase', '')
                    
                    if measurand == 'Current.Import' and phase:
                        currents[phase] = value
                    elif measurand == 'Current.Offered':
                        current_offered = value
                    elif measurand == 'Voltage' and phase:
                        voltages[phase] = value
                    elif measurand == 'Power.Active.Import' and phase:
                        powers[phase] = value
                    elif measurand == 'Power.Offered':
                        power_offered = value
                    elif measurand == 'Frequency':
                        frequency = value
                    elif measurand == 'Energy.Active.Import.Register':
                        total_energy = value
                    elif measurand == 'Energy.Active.Import.Interval':
                        session_energy = value
                        interval_energy_reported = True
                    elif measurand == 'Temperature':
                        temperature = value

                # Log processed values with additional info
                logging.info(f"Power per phase: L1={powers['L1']}W, L2={powers['L2']}W, L3={powers['L3']}W")
                logging.info(f"Current: (L1={currents['L1']}A, L2={currents['L2']}A, L3={currents['L3']}A) Offered={current_offered}A")
                logging.info(f"Voltage: (L1={voltages['L1']}V, L2={voltages['L2']}V, L3={voltages['L3']}V)")
                logging.info(f"Frequency={frequency}Hz, Temperature={temperature}°C")
                logging.info(f"Energy: Session={session_energy}Wh, Total={total_energy}Wh, Power Offered: {power_offered}W")

                # Only compute session energy if not reported directly
                if not interval_energy_reported and self.last_session:
                    session_energy = total_energy - self.last_session.total_energy_start
                    self.last_session.session_energy = max(0, session_energy)
                    logging.info(f"Computed session energy: {session_energy}Wh from total={total_energy}Wh - start={self.last_session.total_energy_start}Wh")

                # Update TWC with latest values
                self.twc.update_from_client(
                    power=sum(powers.values()),
                    currents=currents,
                    voltages=voltages,
                    frequency=frequency,
                    session_energy=self.last_session.session_energy if self.last_session else 0,
                    total_energy=total_energy,
                    pcba_temp_c=temperature,
                    timestamp=timestamp
                )
                
        except Exception as e:
            logging.error(f"Error processing meter values: {e}", exc_info=True)
        
        return call_result.MeterValuesPayload()

    @on(Action.DataTransfer)
    def on_data_transfer(self, vendor_id: str, message_id: str, data: str):
        """Log data transfers from charge point"""
        logging.info(f"Data transfer: vendor={vendor_id}, message={message_id}, data={data}")
        return call_result.DataTransferPayload(status="Accepted")
