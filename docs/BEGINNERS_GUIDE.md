# Beginner's guide

[Back to the README](../README.md) · [Run locally](RUN-LOCALLY.md)

You do not need to understand every tool before trying the app. Start with the local version, file one fictitious claim, and follow that claim through the code.

## Your first visit

1. Follow [Run locally](RUN-LOCALLY.md).
2. Open the Dashboard and inspect one seeded claim in the Claims Tracker.
3. File a new claim using invented information only.
4. Open its details and change Submitted to Under Review with a test note.
5. Reload the page. The saved claim and its history should still be there.

These are demonstration records and workflow states, not actual insurance decisions.

## Follow one claim through the code

| Step | What happens | File |
| --- | --- | --- |
| 1. Fill the form | The browser displays the wizard and gathers your entries. | [app.js](../app/static/app.js), [index.html](../app/static/index.html) |
| 2. Submit | The browser sends a POST request to /api/v1/claims. A route connects the request to the application logic. | [main.py](../app/main.py) |
| 3. Check access and input | The API checks the caller's role and validates the submitted fields. These are required before saving. | [auth.py](../app/auth.py), [schemas.py](../app/schemas.py) |
| 4. Apply claim rules | The service creates the claim, handles duplicate retries, and adds the first history event. | [services.py](../app/services.py) |
| 5. Store and return | The database saves the record; the API returns its details to the browser. | [database.py](../app/database.py) |
| 6. Review later | A status update checks the allowed transition and record version before saving another history event. | [services.py](../app/services.py) |

An **API** is the set of requests another program can send to the app. The browser uses this API too. A future agent would use the same endpoints with its own configured authorization.

An **idempotency key** identifies a submission attempt: retrying the same request with the same key does not create another claim. A **version number** prevents a reviewer from silently overwriting a record that changed since they opened it.

## Understand local versus Azure sign-in

Local development supplies a demo identity with reader, writer, and reviewer roles. It does not test Microsoft sign-in. Keep that mode on your computer.

In Azure, Entra identifies the caller and the API checks its token and roles. Reader can read, Writer can submit, and Reviewer can change status. Roles are independent; Reviewer does not automatically include Reader.

## Where should I look next?

- Screen layout or styling: [index.html](../app/static/index.html) and [app.css](../app/static/app.css).
- Required fields: [schemas.py](../app/schemas.py).
- Allowed status changes: the TRANSITIONS mapping in [services.py](../app/services.py).
- Environment settings: [config.py](../app/config.py).
- How Azure resources fit together: [Architecture](ARCHITECTURE.md).
- How to deploy: [Deployment](DEPLOYMENT.md), then its linked Entra instructions.

You can leave infrastructure and identity setup for later if your goal is to learn the local application.

## Finding your way around the browser code

[app.js](../app/static/app.js) is formatted as one plain JavaScript file:

1. Helpers escape text and format money; `api` handles authorized requests and errors.
2. `dashboard`, `tracker`, and `analytics` render the main screens.
3. `inputField`, `newClaim`, `saveStep`, and `submitStep` implement the wizard.
4. `showClaim` renders details/history, and `navigate` switches screens.
5. The event handlers and `init` connect controls and start sign-in/loading.

Start with the screen you want to change. You do not need a frontend framework or a separate UI build to run this app. Format changes with `npx prettier@3.6.2 --write app/static/app.js`; CI runs JavaScript syntax and focused frontend tests.
