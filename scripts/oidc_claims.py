"""Report only non-secret OIDC trust metadata for the onboarding administrator."""
import base64
import json
import os
import urllib.request


def main():
    url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=api://AzureADTokenExchange"
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"],
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["value"]
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    # This is discovery, not token authentication. Never output the JWT or request token.
    keys = ("sub", "iss", "aud", "repository", "repository_id", "repository_owner_id", "environment", "ref")
    public = {key: claims.get(key) for key in keys}
    print("ONBOARDING_OIDC=" + json.dumps(public, separators=(",", ":")))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write("### GitHub federation metadata\n\n```json\n" + json.dumps(public, indent=2) + "\n```\n")


if __name__ == "__main__":
    main()
