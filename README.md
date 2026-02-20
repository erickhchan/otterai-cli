# otterai-api

Unofficial Python API for [otter.ai](http://otter.ai)

## Contents

-   [Installation](#installation)
-   [Setup](#setup)
-   [CLI](#cli)
-   [APIs](#apis)
    -   [User](#user)
    -   [Speeches](#speeches)
    -   [Speakers](#speakers)
    -   [Folders](#folders)
    -   [Groups](#groups)
    -   [Notifications](#notifications)
-   [Exceptions](#exceptions)

## Installation

`pip install .`

or in a virtual environment

```bash
python3 -m venv env
source env/bin/activate
pip install .
```

## Setup

```python
from otterai import OtterAI
otter = OtterAI()
otter.login('USERNAME', 'PASSWORD')
```

## CLI

A command-line interface is also available for interacting with Otter.ai.

### Authentication

```bash
# Login (saves credentials to ~/.otterai/config.json)
otter login

# Logout (clears saved credentials)
otter logout

# View current user
otter user
```

You can also set credentials via environment variables (these take precedence over the config file):

```bash
export OTTERAI_USERNAME="your-email@example.com"
export OTTERAI_PASSWORD="your-password"
```

### Important: Speech IDs (otid vs speech_id)

Otter.ai speeches have two identifiers:
- **`speech_id`** (e.g. `22WB27HAEBEJYFCA`) — internal ID, does **NOT** work with API endpoints
- **`otid`** (e.g. `jqb7OHo6mrHtCuMkyLN0nUS8mxY`) — the ID used in all API calls

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

## APIs

### User

Get user specific data

```python
otter.get_user()
```

### Speeches

Get all speeches

**optional parameters**: folder, page_size, source

```python
otter.get_speeches()
```

Get speech by id

```python
otter.get_speech(SPEECH_ID)
```

Query a speech

```python
otter.query_speech(QUERY, SPEECH_ID)
```

Upload a speech

**optional parameters**: content_type (default audio/mp4)

```python
otter.upload_speech(FILE_NAME)
```

Download a speech

**optional parameters**: filename (defualt id), format (default: all available (txt,pdf,mp3,docx,srt) as zip file)

```python
otter.download_speech(SPEECH_ID, FILE_NAME)
```

Move a speech to trash

```python
otter.move_to_trash_bin(SPEECH_ID)
```

#### TODO

Start a live speech

### Speakers

Get all speakers

```python
otter.get_speakers()
```

Create a speaker

```python
otter.create_speaker(SPEAKER_NAME)
```

#### TODO

Assign a speaker to speech transcript

### Folders

Get all folders

```python
otter.get_folders()
```

### Groups

Get all groups

```python
otter.list_groups()
```

### Notifications

Get notification settings

```python
otter.get_notification_settings()
```

## Exceptions

```python
from otterai import OtterAIException

try:
 ...
except OtterAIException as e:
 ...
```
