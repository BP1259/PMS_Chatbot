---
title: PMS APPRAISAL CHATBOT
emoji: 📊
colorFrom: blue
colorTo: green
sdk: streamlit
sdk_version: 1.58.0
app_file: app.py
pinned: false
---

# PMS APPRAISAL CHATBOT

Powered by Fireworks AI and Supabase pgvector.

## Setup & deployment

Open **[SETUP.html](SETUP.html)** for the full setup guide:

- local virtualenv setup
- Supabase and Fireworks configuration
- loading the guide data
- deploying on Hugging Face Spaces with native Streamlit SDK 1.58.0

## Required Hugging Face Space secrets

Set these under **Settings -> Variables and secrets**:

- `FIREWORKS_API_KEY`
- `SUPABASE_DB_URL`

Hugging Face installs `requirements.txt` and starts `app.py` automatically.
