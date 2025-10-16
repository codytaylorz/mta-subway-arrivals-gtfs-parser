#!/usr/bin/env bash
# Use a single worker with threads to avoid duplicating large in-memory dataframes
gunicorn -w 1 -k gthread --threads 4 -b 0.0.0.0:$PORT main:app
