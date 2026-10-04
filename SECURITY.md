# Security Policy

## Supported versions

Heptapod is in early development. Security fixes are made on the `main` branch only.

## Reporting a vulnerability

Please do not report security vulnerabilities through public issues.

Report them privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability**. Include a description of the issue, the steps to reproduce it, and the impact you expect.

You can expect an acknowledgement within a few days. Once the issue is confirmed, a fix is prepared and released, and you are credited in the advisory unless you prefer otherwise.

## Scope

Heptapod handles credentials for the systems it connects to. Reports about how credentials are read, cached, sent, or logged are especially welcome. The mock backends in `mocks/` are local test fixtures with throwaway credentials and are not meant to be exposed to a network.
