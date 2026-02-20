# otterai-cli

An unofficial command-line interface for [Otter.ai](https://otter.ai).

> **Note:** This project is not affiliated with or endorsed by Otter.ai / Aisense Inc.

## Installation

```bash
uv tool install otterai-cli
```

This makes the `otter` command available globally.

Or run directly without installing:

```bash
uvx --from otterai-cli otter --help
```

## Setup

```bash
otter login
```

This prompts for your Otter.ai email and password. Credentials are saved to `~/.otterai/config.json`.

### Alternative methods

**Environment variables** (take precedence over config file):

```bash
export OTTERAI_USERNAME="your-email@example.com"
export OTTERAI_PASSWORD="your-password"
```

### Auth commands

```bash
otter user      # check current user
otter logout    # remove saved credentials
```

## Usage

```bash
otter speeches list                          # list all speeches
otter speeches list --days 7                 # last 7 days
otter speeches list --folder "Work"          # by folder name
otter speeches get SPEECH_ID                 # get speech details + transcript
otter speeches download SPEECH_ID -f txt     # download as txt, pdf, mp3, docx, or srt
otter speeches search "keyword" SPEECH_ID    # search within a speech
otter speakers list                          # list all speakers
otter folders list                           # list all folders
```

Run `otter --help` or `otter <command> --help` for more options.

### Important: Speech IDs (otid vs speech_id)

Otter.ai speeches have two identifiers:
- **`speech_id`** (e.g. `22WB27HAEBEJYFCA`) -- internal ID, does **NOT** work with API endpoints
- **`otid`** (e.g. `jqb7OHo6mrHtCuMkyLN0nUS8mxY`) -- the ID used in all API calls

All CLI commands that accept a `SPEECH_ID` argument expect the **otid** value. Use `otter speeches list` to find otids, or `otter speeches list --json | jq '.speeches[].otid'` for just the IDs.

### Speeches

```bash
# List all speeches
otter speeches list

# List with options
otter speeches list --page-size 10 --source owned

# List speeches from the last N days
otter speeches list --days 2

# List speeches in a specific folder (by name or ID)
otter speeches list --folder "CoverNode"

# Get a specific speech
otter speeches get SPEECH_ID

# Search within a speech
otter speeches search "search query" SPEECH_ID

# Download a speech (formats: txt, pdf, mp3, docx, srt)
otter speeches download SPEECH_ID --format txt

# Upload an audio file
otter speeches upload recording.mp4

# Move to trash
otter speeches trash SPEECH_ID

# Rename a speech
otter speeches rename SPEECH_ID "New Title"

# Move speeches to a folder (by name or ID)
otter speeches move SPEECH_ID --folder "CoverNode"
otter speeches move ID1 ID2 ID3 --folder "CoverNode"

# Move to a new folder (auto-create if it doesn't exist)
otter speeches move SPEECH_ID --folder "New Folder" --create
```

### Speakers

```bash
# List all speakers
otter speakers list

# Create a new speaker
otter speakers create "Speaker Name"

# Tag a speaker on transcript segments
otter speakers tag SPEECH_ID SPEAKER_ID
otter speakers tag SPEECH_ID SPEAKER_ID --all
```

### Folders and Groups

```bash
# List folders
otter folders list

# Create a folder
otter folders create "My Folder"

# Rename a folder
otter folders rename FOLDER_ID "New Name"

# List groups
otter groups list
```

### Configuration

```bash
# Show current config
otter config show

# Clear saved config
otter config clear
```

### JSON Output

Most commands support `--json` flag for machine-readable output:

```bash
otter speeches list --json
otter speakers list --json
```

## Development

```bash
uv sync --dev        # install dependencies
uv run pytest        # run tests
```

## Acknowledgements

Based on [gmchad/otterai-api](https://github.com/gmchad/otterai-api) by Chad Lohrli, with CLI functionality from [PR #9](https://github.com/gmchad/otterai-api/pull/9) by [@andrewfurman](https://github.com/andrewfurman).
