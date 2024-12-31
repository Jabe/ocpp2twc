# OCPP to TWC Bridge

This project creates a bridge between OCPP (Open Charge Point Protocol) and Tesla Wall Connector (TWC) protocol. It simulates a TWC while acting as an OCPP server.

## Purpose

This bridge is specifically designed to work with EVCC (Electric Vehicle Charge Controller) to simulate a Tesla Wall Connector. This enables EVCC to directly control Tesla vehicles without requiring TWC hardware, allowing for fine-grained current control down to 1 Ampere using the Tesla API.

Note: It's recommended to use TeslaBleHttpProxy alongside this project to avoid hitting Tesla Fleet API rate limits.

I'm using it with the Fronius Wattpilot.

## About

This project is primarily AI-generated code, developed with the assistance of GitHub Copilot Edits and Claude 3.5 Sonnet.

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
