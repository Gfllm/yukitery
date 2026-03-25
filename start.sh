#!/bin/bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=heelpeers@gmail.com
export SMTP_PASS=mV3uY3vF6ktL3oL
export SECRET_KEY=$(python3 -c "import os; print(os.urandom(32).hex())")

source venv/bin/activate
python app.py
