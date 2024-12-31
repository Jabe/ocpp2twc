# OCPP to TWC Bridge

This project creates a bridge between OCPP (Open Charge Point Protocol) and Tesla Wall Connector (TWC) protocol. It simulates a TWC while acting as an OCPP server.

## Installation

```bash
poetry install
```

## Usage

```bash
poetry run python -m ocpp2twc
```

The server will start on `ws://0.0.0.0:9000` and accept OCPP 1.6 connections.

## Development in VSCode

1. Install the Python extension for VSCode
2. Open the project in VSCode
3. Run `poetry install` in the terminal
4. Select the Python interpreter:
   - Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Type "Python: Select Interpreter"
   - Choose the interpreter from `.venv` folder

To run the server:
- Press `F5` or
- Use the Run and Debug sidebar (Cmd+Shift+D) and click the green play button

## License

MIT
