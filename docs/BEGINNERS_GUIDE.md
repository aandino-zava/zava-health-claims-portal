# Beginner's guide

[Back to the README](../README.md) · [Run locally](RUN-LOCALLY.md)

Start with the local app. File one fictitious claim, then follow it through the code.

## Try the workflow

1. Follow [Run locally](RUN-LOCALLY.md).
2. Open a seeded claim in Claims Tracker.
3. File a new claim with invented information.
4. Change its status from Submitted to Under Review and add a test note.
5. Reload. The saved claim and history should remain.

These are demo records and workflow states, not insurance decisions.

## Follow the code

| Step | What happens | Source |
| --- | --- | --- |
| Fill the form | The browser displays the wizard and collects input. | [app.js](../app/static/app.js), [index.html](../app/static/index.html) |
| Submit | The browser sends `POST /api/v1/claims` to a FastAPI route. | [main.py](../app/main.py) |
| Check access and fields | The API checks the role and validates input before saving. | [auth.py](../app/auth.py), [schemas.py](../app/schemas.py) |
| Apply rules | The service creates a claim, handles duplicate retries, and adds history. | [services.py](../app/services.py) |
| Store and return | The database saves the record; the API returns its details. | [database.py](../app/database.py) |
| Review | An update checks the permitted transition and record version. | [services.py](../app/services.py) |

The **API** is the set of requests another program can send. Both the browser and an authorized agent use it. An **idempotency key** identifies one submission, so retrying the same request does not create another claim. A **version number** prevents a reviewer from overwriting a claim that changed since they opened it.

## Understand access

Local mode supplies Reader, Writer, and Reviewer automatically. In Azure, Entra identifies the caller and the API checks the token and roles. Roles are independent; Reviewer does not include Reader. Keep development authentication on your computer.

The working Azure demo uses App Service in Central US and private PostgreSQL in East US 2. [Automated onboarding](DEPLOYMENT.md#automated-onboarding) handles identities, GitHub settings, deployment, and the redirect URL after administrator sign-in.

## Find the part you want to change

- Screens and styling: [index.html](../app/static/index.html), [app.css](../app/static/app.css).
- Required fields: [schemas.py](../app/schemas.py).
- Allowed status changes: `TRANSITIONS` in [services.py](../app/services.py).
- Environment settings: [config.py](../app/config.py).
- Azure components and design choices: [Architecture](ARCHITECTURE.md).

[app.js](../app/static/app.js) is one plain JavaScript file. Helpers handle escaping, formatting, and API calls; `dashboard`, `tracker`, and `analytics` render screens; the form functions implement the wizard; `showClaim` displays history; event handlers and `init` start the app. No frontend framework or separate UI build is required.

Format JavaScript changes with `npx prettier@3.6.2 --write app/static/app.js`, then run the syntax and frontend checks in [Validation](VALIDATION.md).
