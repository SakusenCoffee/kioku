"""Write an AltStore source (JSON) for one Kioku iOS release to stdout.

AltStore installs and updates apps from sources: users add the source URL
once (the release's altstore.json, see .github/workflows/ios.yml).
"""

import argparse
import datetime
import json

parser = argparse.ArgumentParser()
parser.add_argument("--version", required=True)
parser.add_argument("--build", required=True)
parser.add_argument("--size", type=int, required=True)
parser.add_argument("--download", required=True)
parser.add_argument("--repo", required=True, help="owner/name on GitHub")
args = parser.parse_args()

raw = f"https://raw.githubusercontent.com/{args.repo}/main"
release = f"https://github.com/{args.repo}/releases"
description = (
    "The real Anki desktop app (aqt) running natively on iPhone and iPad: "
    "the same deck list, reviewer, browser, statistics, deck options and "
    "add-ons as on your computer, with your own collection and AnkiWeb sync."
)
source = {
    "name": "Kioku",
    "identifier": "io.ankidesk.kioku.source",
    "sourceURL": f"{release}/latest/download/altstore.json",
    "subtitle": "Anki desktop, native on iOS",
    "description": description,
    "iconURL": f"{raw}/shared/icon/kioku-1024.png",
    "website": f"https://github.com/{args.repo}",
    "tintColor": "2563EB",
    "apps": [
        {
            "name": "Kioku",
            "bundleIdentifier": "io.ankidesk.kioku",
            "developerName": args.repo.split("/")[0],
            "subtitle": "Anki desktop, native on iOS",
            "localizedDescription": description,
            "iconURL": f"{raw}/shared/icon/kioku-1024.png",
            "tintColor": "2563EB",
            "category": "education",
            "screenshots": [
                f"{raw}/docs/images/ios-{name}.png"
                for name in ("decks", "review-question", "review-answer", "browse", "stats")
            ],
            "versions": [
                {
                    "version": args.version,
                    "buildVersion": args.build,
                    "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "localizedDescription": f"Kioku {args.version}. Release notes: {release}/tag/v{args.version}",
                    "downloadURL": args.download,
                    "size": args.size,
                    "minOSVersion": "16.0",
                }
            ],
            "appPermissions": {"entitlements": [], "privacy": {}},
        }
    ],
    "news": [],
}
print(json.dumps(source, indent=2))
