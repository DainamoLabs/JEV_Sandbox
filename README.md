# Jevos playground

A minimal local demo for recording Jevos decisions. Includes the `PLAIN`,
`MULTI_QUESTION`, and `CONVERSATION_HISTORY` examples from `response.py`, plus:

- **Happy customer:** satisfaction, delivery problems, and refund requests.
- **Return policy:** a final-sale exclusion despite being within the return window.
- **Email triage:** a requested action that is not urgent today.
- **Bug report:** a repeatable crash, saved data, and an available workaround.

All answers are generated live by the model; the examples have no fixed results.

```bash
python -m pip install -r requirements.txt
./run.sh
```

Open **http://127.0.0.1:8000** with your Jevos llama.cpp server running on port 8080.
For a different backend or web port:

```bash
./run.sh --llama-url http://127.0.0.1:8080 --port 8000
```

Choose an example, edit the context or questions, and click **Run decisions**
(or **Ctrl/Cmd + Enter**). Results show the probability of **yes**, a yes/no decision
at a 50% threshold, and elapsed time for the whole request. Changing an input clears
old results. **Reset example** restores the selected preset.

For recording, use your browser's full-screen mode (usually F11) and increase zoom
as needed. All assets are local; there are no remote fonts, analytics, or canned results.

The page calls the Python app, which reuses `response.ask_jev()` to query llama.cpp.
The model must be Jevos: its trained labels are `0` and `1`, and it uses the
`<evidence>` prompt. A general chat model needs a different adapter.

Validation: `python -m unittest -v`.
