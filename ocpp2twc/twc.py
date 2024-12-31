import asyncio
import json
import logging
from aiohttp import web
from dataclasses import dataclass, field
from typing import List, Any, Dict
from datetime import datetime, timezone

@dataclass
class Vitals:
    contactor_closed: bool = False
    vehicle_connected: bool = False
    session_s: int = 0
    grid_v: float = 0.0
    grid_hz: float = 0.0
    vehicle_current_a: float = 0.0
    currentA_a: float = 0.0
    currentB_a: float = 0.0
    currentC_a: float = 0.0
    currentN_a: float = 0.0
    voltageA_v: float = 0.0
    voltageB_v: float = 0.0
    voltageC_v: float = 0.0
    relay_coil_v: float = 0.0
    pcba_temp_c: float = 0.0
    handle_temp_c: float = 0.0
    mcu_temp_c: float = 0.0
    uptime_s: int = 0
    input_thermopile_uv: float = 0.0
    prox_v: float = 0.0
    pilot_high_v: float = 0.0
    pilot_low_v: float = 0.0
    session_energy_wh: float = 0.0
    total_energy_wh: float = 0.0  # Add total energy counter
    config_status: int = 0
    evse_state: int = 0
    current_alerts: List[Any] = field(default_factory=list)

    def to_dict(self):
        return {k: v if v is not None else [] for k, v in self.__dict__.items()}

class TWCSimulator:
    EVSE_STATES = {
        0: "unknown",
        1: "disabled",
        2: "ready",
        3: "charging",
        4: "error"
    }

    def __init__(self):
        self.vitals = Vitals()
        self.max_power = 11000  # 11kW
        self.start_time = datetime.now(timezone.utc)
        self.charging_start_time = None
        self.ocpp_connected = False
        self.last_seen = datetime.now(timezone.utc).timestamp()

    @property
    def charging(self):
        """Derive charging state from vitals"""
        return self.vitals.contactor_closed and self.vitals.evse_state == 3

    def set_enabled(self, enabled: bool):
        """Update enabled state"""
        if enabled:
            if self.vitals.evse_state == 4:  # error
                return False
            if self.vitals.vehicle_connected:
                self.vitals.evse_state = 3  # charging
                self.vitals.contactor_closed = True
                if not self.charging_start_time:
                    self.charging_start_time = datetime.now(timezone.utc)
            else:
                self.vitals.evse_state = 2  # ready
        else:
            self.vitals.evse_state = 1  # disabled
            self.vitals.contactor_closed = False
            self.charging_start_time = None
        return True

    def set_vehicle_connected(self, connected: bool):
        """Update vehicle connection state"""
        was_connected = self.vitals.vehicle_connected
        self.vitals.vehicle_connected = connected
        
        if connected != was_connected:
            logging.info(f"Vehicle {'connected' if connected else 'disconnected'}")
        
        if not connected:
            self.vitals.contactor_closed = False
            self.charging_start_time = None
            if self.vitals.evse_state != 1 and self.vitals.evse_state != 4:  # if not disabled or error
                self.vitals.evse_state = 2  # go to ready
        elif self.vitals.evse_state == 2:  # if in ready state
            self.vitals.evse_state = 3  # start charging
            self.vitals.contactor_closed = True
            if not self.charging_start_time:
                self.charging_start_time = datetime.now(timezone.utc)
        
        return True

    def set_error(self, has_error: bool):
        """Set error state"""
        if has_error:
            self.vitals.evse_state = 4  # error
            self.vitals.contactor_closed = False
            self.charging_start_time = None
        else:
            self.vitals.evse_state = 1  # start in disabled state
            self.set_enabled(True)  # then try to enable

    def set_ocpp_connected(self, connected: bool):
        """Update OCPP connection state"""
        self.ocpp_connected = connected
        if connected:
            self.last_seen = datetime.now(timezone.utc).timestamp()
        else:
            self.vitals.evse_state = 0  # unknown
            self.vitals.contactor_closed = False
            self.charging_start_time = None

    def update_from_client(self, power: float, currents: dict, voltages: dict, 
                         frequency: float = 50.0, session_energy: float = 0,
                         total_energy: float = 0, pcba_temp_c: float = 20, timestamp: str = None):
        """Update vitals with values from OCPP client"""
        now = datetime.now(timezone.utc)
        
        # Update all electrical values directly from client
        self.vitals.currentA_a = currents.get('L1', 0)
        self.vitals.currentB_a = currents.get('L2', 0)
        self.vitals.currentC_a = currents.get('L3', 0)
        self.vitals.currentN_a = currents.get('N', 0)
        
        # Sum of phase currents for vehicle total
        self.vitals.vehicle_current_a = sum(
            c for c in [self.vitals.currentA_a, 
                       self.vitals.currentB_a, 
                       self.vitals.currentC_a] if c > 0
        )
        
        # Update voltages per phase
        self.vitals.voltageA_v = voltages.get('L1', 230.0)
        self.vitals.voltageB_v = voltages.get('L2', 230.0)
        self.vitals.voltageC_v = voltages.get('L3', 230.0)
        
        # Calculate grid voltage as average of phases
        active_voltages = [v for v in [self.vitals.voltageA_v, 
                                     self.vitals.voltageB_v, 
                                     self.vitals.voltageC_v] if v > 2.0]
        self.vitals.grid_v = sum(active_voltages) / len(active_voltages) if active_voltages else 230.0
        self.vitals.grid_hz = frequency
        
        # Update both energy counters
        self.vitals.session_energy_wh = session_energy
        self.vitals.total_energy_wh = total_energy
        
        # Update session time if we're charging
        if self.charging_start_time:
            if timestamp:
                try:
                    charge_time = datetime.fromisoformat(timestamp)
                    self.vitals.session_s = int((charge_time - self.charging_start_time).total_seconds())
                except ValueError:
                    self.vitals.session_s = int((now - self.charging_start_time).total_seconds())
        else:
            self.vitals.session_s = 0
            
        # Update pilot signal values based on state
        self.vitals.pilot_high_v = 12.0 if self.vitals.evse_state in (2, 3) else 0.0
        self.vitals.pilot_low_v = 12.0 if self.vitals.evse_state in (2, 3) else 0.0
        self.vitals.relay_coil_v = 12.0 if self.vitals.contactor_closed else 0.0
        
        # Update uptime
        self.vitals.uptime_s = int(now.timestamp() - self.start_time.timestamp())
        
        # Fixed temperature values
        self.vitals.pcba_temp_c = pcba_temp_c
        self.vitals.handle_temp_c = 20.0
        self.vitals.mcu_temp_c = 20.0
        
        return True

    def set_power(self, watts: int):
        self.current_power = min(watts, self.max_power)
        return True

    def get_state(self):
        return self.state

    async def handle_twc3_request(self, request):
        """Handle TWC3 HTTP API requests"""
        if request.method == 'GET':
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET',
                'Access-Control-Allow-Headers': 'Content-Type'
            }

            if not self.ocpp_connected:
                response = {
                    "error": "OCPP client not connected",
                    "state": self.EVSE_STATES.get(0, "unknown"),
                    "status": "offline"
                }
                return web.json_response(response, headers=headers, status=503)

            # Log vitals for debugging
            logging.debug(f"Current vitals state: {self.vitals.to_dict()}")
            return web.json_response(self.vitals.to_dict(), headers=headers)

        return web.Response(status=405)

    async def start_twc3_server(self):
        """Start TWC3 HTTP server"""
        app = web.Application()
        app.router.add_route('*', '/api/1/vitals', self.handle_twc3_request)
        
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
        await site.start()
        return site
