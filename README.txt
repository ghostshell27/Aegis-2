Aegis 2 -- AI-powered Algebra and Calculus tutor
==================================================

HOW TO RUN FROM A USB DRIVE
---------------------------
1. Copy the entire "Aegis2" folder onto your USB stick.
2. On any Windows PC, open the folder and double-click "Aegis2.exe".
3. A console window opens and your default browser launches at a local
   address such as http://127.0.0.1:8765. Keep the console open while
   you study -- closing it shuts down the app.

FIRST LAUNCH
------------
The first time you run the app you will be taken to the configuration
screen. Provide:

  * API key       -- your AI provider's secret key.
  * Base URL      -- defaults to https://api.anthropic.com. Works with any
                     OpenAI-compatible endpoint (OpenRouter, Chutes, a
                     self-hosted proxy, etc.).
  * Model name    -- e.g. "claude-opus-4-7", "gpt-4o-mini",
                     "meta-llama/Meta-Llama-3.1-70B-Instruct", etc.
  * System prompt -- optional free-form instructions that are prepended to
                     every AI interaction. Examples:
                         "Respond like a strict professor."
                         "Reply only in Spanish."
                         "Use the Socratic method aggressively."

The configuration is saved to data\userdata.db, encrypted with a key
derived from this machine's hostname. Copying the USB to a different
machine will ask you to configure again -- by design.

DATA PORTABILITY
----------------
Everything the app writes lives inside this folder:

  data\userdata.db     -- your progress, session history, profile
  data\curriculum.json -- read-only track structure

BACKUP & RESTORE (RECOMMENDED BEFORE UPDATING)
----------------------------------------------
Inside the app, open Settings. Two buttons at the bottom:

  * Export progress  -- downloads a single .db file containing every
                        session, your mastery scores, error patterns,
                        capstone state, and your encrypted API key.
                        Save this somewhere safe.
  * Import progress  -- upload a previously-exported .db file to restore.
                        The current data is moved aside as
                        data\userdata.db.bak so you can roll back if the
                        new file turns out to be wrong.

After import, reload the page (Ctrl+R) to see the restored data.

CURRICULUM OVERVIEW
-------------------
Two tracks are available on the home screen:

  ALGEBRA  -- 10 units from real numbers to sequences, capped by a
              full-business-model capstone problem.
  CALCULUS -- 10 units from precalculus bridge to transcendental
              functions, capped by a structural-optimization capstone.

Each topic is taught by the AI using a hook scenario, a step-by-step
explanation, a worked example, and progressively harder exercises.
When you answer wrong, the AI narrates the real-world consequence of
your mistake (never a generic "try again"). You can type "no se",
"I don't know", or click the visible button to trigger a Socratic
guided walkthrough at any time.

UPDATING THE APP WITHOUT LOSING PROGRESS
----------------------------------------
The simplest workflow:
  1. Open Settings -> Export progress, save the .db somewhere.
  2. Replace your portable folder with the new build.
  3. Open Settings -> Import progress, pick the saved .db.

Or, if you prefer in-place updates:
  Replace ONLY Aegis2.exe and the _internal\ folder with the new build's
  versions. Leave the data\ folder alone. Schema upgrades happen
  automatically on launch.

BUILDING FROM SOURCE
--------------------
Requirements: Python 3.11+, Node.js 18+.

    build.bat

Produces dist\Aegis2\Aegis2.exe along with a data\ folder.

The build script will refuse to start if Python or Node.js are missing and
will pause on any error so you can read it. If you do not have Node.js
installed yet, get the LTS installer from https://nodejs.org/, reopen the
console window so PATH refreshes, and run build.bat again.

RUNNING FROM SOURCE WITHOUT BUILDING
------------------------------------
You don't need Node.js just to test the backend. Once `venv` is set up
(either by build.bat creating it or by you running `python -m venv venv`
+ `pip install -r requirements.txt` manually), launch with:

    launch_dev.bat

This uses the project venv's Python. If you have not built the frontend
yet, the root URL serves a placeholder page; the API at /api/health works
either way. To get the full UI, run build.bat to produce static\.

TROUBLESHOOTING
---------------
* If the browser does not open, copy the URL printed in the console
  into your browser manually.
* If an AI call fails, the app shows a retry button; double-check your
  API key and base URL in the configuration screen.
* Firewall prompts: the app only listens on 127.0.0.1, so you can
  safely deny external access without breaking anything.
