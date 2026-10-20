"""Catch missing guides, misplaced content, broken local links and startup syntax errors."""
import ast
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = {
    "README.md": "# Health Claims Portal",
    "docs/BEGINNERS_GUIDE.md": "# Beginner's guide",
    "docs/ARCHITECTURE.md": "# How the application fits together",
    "docs/RUN-LOCALLY.md": "# Run the demo on your computer",
    "docs/DEPLOYMENT.md": "# Deploy your demo to Azure",
    "docs/AUTH.md": "# Entra configuration",
    "docs/API.md": "# Connect an agent to the claims API",
    "docs/VALIDATION.md": "# Check your demo",
    "docs/COPILOT_STUDIO.md": "# Connect Copilot Studio",
}


def check(root):
    errors = []
    for name, heading in HEADINGS.items():
        path = root / name
        if not path.is_file():
            errors.append(f"Missing required document: {name}")
            continue
        content = path.read_text(encoding="utf-8")
        if content.splitlines()[:1] != [heading]:
            errors.append(f"{name}: expected first line {heading!r}; check for misplaced content.")
        if len(re.findall(r"^```", content, re.MULTILINE)) % 2:
            errors.append(f"{name}: unbalanced fenced code blocks.")
        prose = re.sub(r"^```.*?^```[^\n]*", "", content, flags=re.MULTILINE | re.DOTALL)
        if re.search(r"^(?:from \w[\w.]* import |import \w|def \w+\(|class \w+[:(])", prose, re.MULTILINE):
            errors.append(f"{name}: Python statements outside code fences; check file contents.")
        for target in re.findall(r"\]\(([^)]+)\)", prose):
            link = urlsplit(target)
            if link.scheme or link.netloc or not link.path:
                continue
            resolved = (path.parent / unquote(link.path)).resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.exists():
                errors.append(f"{name}: broken repository link {target!r}.")
    try:
        source = (root / "app/start.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="app/start.py")
        compile(tree, "app/start.py", "exec")
        if not any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in tree.body):
            errors.append("app/start.py: missing main function; check for misplaced content.")
    except (OSError, SyntaxError) as exc:
        errors.append(f"app/start.py: cannot compile ({type(exc).__name__}).")
    return errors


def main():
    errors = check(ROOT)
    for error in errors:
        print(error)
    if not errors:
        print("Repository sanity checks passed.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
