# NOOP Push

NOOP Push is a Home Assistant custom integration for receiving NOOP health data.

Milestone 1 provides a bearer-authenticated capabilities endpoint at
`/api/noop/push`. Configure the integration through Home Assistant and use the
stable endpoint state ID returned by `GET`.

Use HTTPS whenever the endpoint is reachable through a hostname or public
network. The bearer token is stored in the Home Assistant config entry and is
never included in entity state.
