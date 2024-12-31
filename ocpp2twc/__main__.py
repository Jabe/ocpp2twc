import asyncio
import logging
import websockets
from websockets.server import WebSocketServerProtocol

from .server import ChargePoint
from .twc import TWCSimulator

logging.basicConfig(level=logging.DEBUG)  # Change to DEBUG level

async def on_connect(websocket: WebSocketServerProtocol, path: str, twc: TWCSimulator):
    """Handle incoming WebSocket connection"""
    try:
        cp = ChargePoint("TWC3_CHARGER", websocket, twc)
        await cp.start()
    except Exception as e:
        logging.error(f"Error in OCPP connection: {e}")
    finally:
        if not websocket.closed:
            await websocket.close()

async def main():
    twc = TWCSimulator()
    
    # Start TWC3 server
    await twc.start_twc3_server()
    logging.info("TWC3 Server started on http://0.0.0.0:8080")
    
    # Start OCPP server
    server = await websockets.serve(
        lambda ws, path: on_connect(ws, path, twc),
        '0.0.0.0',
        9000,
        subprotocols=['ocpp1.6']
    )
    logging.info("OCPP Server started on ws://0.0.0.0:9000")
    
    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        logging.info("Shutting down servers...")
        server.close()
        await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
