import asyncio
import logging
import time
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call
from ocpp.v16.enums import Action, ChargePointStatus
import websockets
from datetime import datetime, timezone
import math
import random

logging.basicConfig(level=logging.INFO)

class SimulatedChargePoint(cp):
    def __init__(self, id, connection):
        super().__init__(id, connection)
        self.current_power = 0
        self.max_power = 11000  # 11kW
        self.charging = False
        self.vehicle_connected = False
        self.enabled = False
        self.current = 16  # default charging current
        self.voltage = 230  # assume 230V
        self.session_energy = 0
        self.start_time = datetime.now(timezone.utc)
        self.base_voltage = 230
        self.base_current = 10
        self.base_frequency = 50.0
        self.last_update = datetime.now(timezone.utc).timestamp()
        self.total_energy_wh = 0  # Total energy counter in Wh
        self.charging_start_time = None
        self.authorized = False
        self.transaction_id = None
        self.last_transaction_id = None  # Keep track of last transaction ID

    def set_enabled(self, enabled: bool):
        """Update enabled state and handle EVSE suspension"""
        if not enabled:
            if self.charging:
                # Suspend charging from EVSE side
                asyncio.create_task(self.send_status_notification(ChargePointStatus.suspended_evse))
                self.charging = False
                logging.info("Charging suspended by EVSE")

    async def start_charging_session(self):
        """Start a charging session after delay"""
        await asyncio.sleep(5)
        
        # Authorize first
        auth_response = await self.call(call.AuthorizePayload(
            id_tag="TEST"
        ))
        if auth_response.id_tag_info['status'] == 'Accepted':
            self.authorized = True
            
            # Start transaction
            start_response = await self.call(call.StartTransactionPayload(
                connector_id=1,
                id_tag="TEST",
                meter_start=0,
                timestamp=datetime.now(timezone.utc).isoformat()
            ))
            self.transaction_id = start_response.transaction_id
            logging.info(f"Transaction started with ID: {self.transaction_id}")
            
            # Update status
            self.vehicle_connected = True
            self.charging = True
            self.charging_start_time = datetime.now(timezone.utc)
            await self.send_status_notification(ChargePointStatus.charging)
            logging.info("Vehicle connected and charging started")

    async def stop_charging(self):
        """Stop charging session"""
        if self.transaction_id:
            logging.info(f"Stopping transaction ID: {self.transaction_id}")
            await self.call(call.StopTransactionPayload(
                meter_stop=int(self.session_energy),
                timestamp=datetime.now(timezone.utc).isoformat(),
                transaction_id=self.transaction_id,
                reason="Local"
            ))
            self.last_transaction_id = self.transaction_id  # Store last ID
            self.transaction_id = None
            logging.info(f"Last transaction ID stored: {self.last_transaction_id}")
        
        self.charging = False
        await self.send_status_notification(ChargePointStatus.suspended_ev)
        logging.info("Charging stopped")

    def get_grid_values(self):
        """Simulate realistic grid variations"""
        now = datetime.now(timezone.utc).timestamp()
        t = now - self.last_update

        # Voltage variation: ±5% with slow oscillation and noise
        voltage_variation = (
            math.sin(t * 0.1) * 2.0 +                # Slow oscillation
            math.sin(t * 1.0) * 1.0 +                # Medium oscillation
            random.uniform(-0.5, 0.5)                # Random noise
        )
        voltage = self.base_voltage + voltage_variation

        current = self.base_current

        # Frequency variation: ±0.1Hz with very slow oscillation
        freq_variation = (
            math.sin(t * 0.05) * 0.1 +              # Very slow oscillation
            random.uniform(-0.01, 0.01)              # Tiny random noise
        )
        frequency = self.base_frequency + freq_variation

        return voltage, current, frequency

    async def simulate_power_draw(self):
        """Simulate realistic power consumption"""
        # Start charging session in background
        asyncio.create_task(self.start_charging_session())
        
        while True:
            voltage, current, frequency = self.get_grid_values()
            now = datetime.now(timezone.utc)
            self.last_update = now.timestamp()
            
            if self.charging and self.vehicle_connected:
                # Base power calculation with realistic variations
                nominal_power = self.current * voltage * 3  # 3-phase
                
                # Add load-based variations
                time_factor = math.sin(datetime.now().timestamp() * 0.05)  # Slower oscillation
                power_variation = (
                    time_factor * nominal_power * 0.02 +  # 2% slow power oscillation
                    random.uniform(-50, 50)               # Random noise ±50W
                )
                
                self.current_power = min(nominal_power + power_variation, self.max_power)
                energy_increment = self.current_power * (5/3600)  # 5s in hours
                self.session_energy += energy_increment
                self.total_energy_wh += energy_increment

                # Stop charging after 100 Wh
                if self.session_energy >= 100:
                    await self.stop_charging()
                    logging.info("Charging stopped after reaching 100 Wh")
            else:
                self.current_power = 0
                current = 0

            # Build meter values with per-phase measurements
            sampled_values = [
                # Power measurements
                {
                    "value": str(round(self.current_power, 2)),
                    "context": "Sample.Periodic",
                    "format": "Raw",
                    "measurand": "Power.Active.Import",
                    "unit": "W"
                },
                # Phase voltages
                {
                    "value": str(round(voltage, 2)),
                    "measurand": "Voltage",
                    "unit": "V",
                    "phase": "L1"
                },
                {
                    "value": str(round(voltage, 2)),
                    "measurand": "Voltage",
                    "unit": "V",
                    "phase": "L2"
                },
                {
                    "value": str(round(voltage, 2)),
                    "measurand": "Voltage",
                    "unit": "V",
                    "phase": "L3"
                },
                # Phase currents
                {
                    "value": str(round(current, 2)),
                    "measurand": "Current.Import",
                    "unit": "A",
                    "phase": "L1"
                },
                {
                    "value": str(round(current, 2)),
                    "measurand": "Current.Import",
                    "unit": "A",
                    "phase": "L2"
                },
                {
                    "value": str(round(current, 2)),
                    "measurand": "Current.Import",
                    "unit": "A",
                    "phase": "L3"
                },
                # Frequency
                {
                    "value": str(round(frequency, 3)),
                    "measurand": "Frequency",
                    "unit": "Hertz"
                },
                # Energy counters
                {
                    "value": str(round(self.total_energy_wh, 2)),
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh"
                },
                {
                    "value": str(round(self.session_energy, 2)),
                    "measurand": "Energy.Active.Import.Interval",
                    "unit": "Wh"
                }
            ]

            # Send meter values
            try:
                response = await self.call(call.MeterValuesPayload(
                    connector_id=1,
                    meter_value=[{
                        "timestamp": now.isoformat(),
                        "sampled_value": sampled_values
                    }]
                ))
                
                if self.charging:
                    logging.info(f"Charging: {round(self.current_power/1000, 2)} kW, "
                               f"V(L1/L2/L3): {round(voltage,1)}V, F: {round(frequency,2)}Hz, "
                               f"Session: {round(self.session_energy/1000, 2)} kWh")
                    
            except Exception as e:
                logging.error(f"Error sending MeterValues: {e}")

            await asyncio.sleep(5)

    async def start(self):
        """Handle OCPP messages"""
        asyncio.create_task(self.simulate_power_draw())
        try:
            await super().start()
        except Exception as e:
            logging.error(f"Error in message loop: {e}")
            raise

    async def send_boot_notification(self):
        request = call.BootNotificationPayload(
            charge_point_vendor="Tesla",
            charge_point_model="Wall Connector 3"
        )
        try:
            response = await self.call(request)
            logging.info(f"BootNotification response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error sending BootNotification: {e}")
            raise

    async def send_status_notification(self, status: ChargePointStatus):
        request = call.StatusNotificationPayload(
            connector_id=1,
            error_code="NoError",
            status=status
        )
        try:
            await self.call(request)
        except Exception as e:
            logging.error(f"Error sending StatusNotification: {e}")

    async def send_heartbeat(self):
        try:
            request = call.HeartbeatPayload()
            response = await self.call(request)
            logging.info(f"Heartbeat response: {response}")
            return response
        except Exception as e:
            logging.error(f"Error sending Heartbeat: {e}")
            raise

async def main():
    try:
        async with websockets.connect(
            "ws://0.0.0.0:9000",
            subprotocols=["ocpp1.6"]
        ) as ws:
            cp = SimulatedChargePoint("TWC3_SIM", ws)
            
            # Start message handling in background
            message_loop = asyncio.create_task(cp.start())

            # Send initial boot notification and status
            await cp.send_boot_notification()
            await cp.send_status_notification(ChargePointStatus.available)

            # Separate heartbeat loop
            heartbeat_interval = 30
            last_heartbeat = 0
            
            while True:
                try:
                    now = time.time()
                    if now - last_heartbeat >= heartbeat_interval:
                        await cp.send_heartbeat()
                        last_heartbeat = now
                    await asyncio.sleep(1)  # Check heartbeat every second
                except Exception as e:
                    logging.error(f"Error in main loop: {e}")
                    break

            message_loop.cancel()
            try:
                await message_loop
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logging.error(f"Connection error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Shutting down client...")