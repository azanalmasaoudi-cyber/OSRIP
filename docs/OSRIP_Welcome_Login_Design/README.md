# OSRIP — Premium Welcome & Username/Password Sign-In Design

This is a **self-contained interactive visual reference** for the existing OSRIP app. Open `index.html` in any modern browser; no server, API key, npm packages or network access are needed.

## Contents

- `index.html` — responsive welcome screen, username/password sign-in screen, language and theme switches, show/hide password.
- `assets/osrip_electricity.png`, `osrip_water.png`, `osrip_food_security.png`, `osrip_trade.png` — the user's four original OSRIP sector cards, reused unchanged.
- `OSRIP_Welcome_Desktop.png`, `OSRIP_Login_Desktop.png` — visual previews of both screens.
- `CLAUDE_IMPLEMENTATION_PROMPT.md` — instructions for implementing the design in the real OSRIP repository.

## SECURITY / IMPLEMENTATION NOTICE

**This is a design prototype, not a working authentication system.** Form submission shows a demo notice and clears the password. It never saves credentials, authenticates, creates admin privileges, or makes a network request. Claude must wire the username/password form into the existing backend auth and preserve robust password hashing, session security, account migration, RBAC, and recovery options. Do not deploy this standalone demo as a production login.

Both Enter Platform and Skip Introduction route to the sign-in design only for demonstration; actual OSRIP should retain permitted guest access and the current introduction flow.
