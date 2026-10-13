import argparse
import json
import logging
import math
import requests

LLAMA_URL = "http://127.0.0.1:8080"
REQUEST_TIMEOUT = 60
logger = logging.getLogger(__name__)


def _yes_probability(data):
    """Read Jevos' trained labels: 1 means yes, 0 means no."""
    completions = data.get("completion_probabilities")
    if not completions:
        raise RuntimeError("llama.cpp returned no completion probabilities.")

    completion = completions[0]
    # llama.cpp versions use either log probabilities or ordinary probabilities.
    if "top_logprobs" in completion:
        candidates = completion["top_logprobs"]
        use_logprobs = True
    elif "top_probs" in completion:
        candidates = completion["top_probs"]
        use_logprobs = False
    elif "probs" in completion:
        candidates = completion["probs"]
        use_logprobs = False
    else:
        raise RuntimeError("Unrecognized llama.cpp token probability format.")

    scores = []
    for item in candidates:
        token = item.get("token", item.get("tok_str", "")).strip().lower()
        if token in ("1", "0"):
            score = item["logprob"] if use_logprobs else item["prob"]
            # llama.cpp encodes log(0) as approximately -3.4e38, not -inf.
            # These are zero probabilities, not tiny scores we can rescale.
            if use_logprobs and (score is None or score <= -1e30):
                continue
            scores.append((token, score))

    if use_logprobs and scores:
        # Scale before exponentiating so very small probabilities do not underflow.
        largest = max(score for _, score in scores)
        scores = [
            (token, math.exp(score - largest) if largest != -math.inf else 0.0)
            for token, score in scores
        ]

    yes_prob = sum(score for token, score in scores if token == "1")
    total = sum(score for _, score in scores)
    if total == 0:
        raise RuntimeError(
            "Could not find Jevos labels 0 or 1 with nonzero probability in the "
            "returned token probabilities. Check that the server is running the "
            "Jevos model and supports post_sampling_probs. "
            f"Generated content: {data.get('content')!r}. "
            "Run python response.py --debug to inspect the server response."
        )

    return yes_prob / total


def get_noul_probability(state, question):
    if not isinstance(state, str):
        state = json.dumps(state, indent=2)

    # Jevos is a binary classifier. Use the training prompt, not the inherited
    # chat template (which inserts <think> and scores an unrelated context).
    # Source: feder-cr/jev, export/export_openvino.py, validate().
    prompt = f"<s><evidence>\n{state}\n</evidence>\n\n" f"Question: {question}\nAnswer:"

    # The trained output labels are the single tokens 0 (no) and 1 (yes).
    # Temperature 1 and no filtering preserve their relative probabilities;
    # greedy sampling would collapse post-sampling probabilities to 0 or 1.
    response = requests.post(
        f"{LLAMA_URL}/completion",
        json={
            "prompt": prompt,
            "n_predict": 1,
            "grammar": 'root ::= "0" | "1"',
            "temperature": 1.0,
            "samplers": ["temperature"],
            "n_probs": 2,
            "post_sampling_probs": True,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    logger.debug(
        "llama.cpp response: %s",
        json.dumps(
            {
                "model": data.get("model"),
                "prompt": data.get("prompt", prompt),
                "content": data.get("content"),
                "generation_settings": data.get("generation_settings"),
                "completion_probabilities": data.get("completion_probabilities"),
            },
            indent=2,
        ),
    )
    return _yes_probability(data)


def ask_jev(request):
    state = request["state"]
    questions = request["questions"]

    answers = {}

    if isinstance(questions, dict):
        named_questions = questions.items()
    else:
        named_questions = ((q["name"], q) for q in questions)

    for name, q in named_questions:
        q_type = q["type"]

        if q_type != "noul":
            raise ValueError(f"Unsupported question type: {q_type}")

        probability = get_noul_probability(state, q["instructions"])

        answers[name] = {"type": "noul", "noul": round(probability, 4)}

    return {"answers": answers}


PLAIN = {
    "model": "jev-latest",
    "state": "The package arrived damaged and the screen is cracked.",
    "questions": {
        "damaged": {"type": "noul", "instructions": "Is the product damaged?"}
    },
}

MULTI_QUESTION = {
    "model": "jev-latest",
    "state": {
        "customer_message": "My order still hasn't arrived and it's been three weeks. I want my money back.",
        "delivery_status": "Not delivered",
        "days_since_order": 21,
    },
    "questions": {
        "refund_request": {
            "type": "noul",
            "instructions": "Is the customer asking for a refund?",
        },
        "delivery_problem": {
            "type": "noul",
            "instructions": "Is this primarily a delivery problem?",
        },
        "angry_customer": {
            "type": "noul",
            "instructions": "Does the customer appear upset?",
        },
    },
}

CONVERSATION_HISTORY = {
    "model": "jev-latest",
    "state": [
        {"author": "customer", "message": "When will my order arrive?"},
        {"author": "support", "message": "It should arrive tomorrow."},
        {"author": "customer", "message": "You told me that three days ago."},
    ],
    "questions": {
        "unresolved": {
            "type": "noul",
            "instructions": "Is the customer's problem still unresolved?",
        },
        "frustrated": {
            "type": "noul",
            "instructions": "Does the customer appear frustrated?",
        },
    },
}


CLASSIFICATION = {
    "model": "jev-latest",
    "state": [
        {"author": "customer", "message": "When will my order arrive?"},
        {"author": "support", "message": "It should arrive tomorrow."},
        {"author": "customer", "message": "You told me that three days ago."},
    ],
    "questions": {
        "unresolved": {
            "type": "noul",
            "instructions": "Is the customer's problem still unresolved?",
        },
        "frustrated": {
            "type": "noul",
            "instructions": "Does the customer appear frustrated?",
        },
    },
}


HAPPY_CUSTOMER = {
    "model": "jev-latest",
    "state": (
        "My headphones arrived two days early and work perfectly. "
        "The sound is fantastic. I'm keeping them and have already recommended "
        "your store to a friend. Thank you!"
    ),
    "questions": {
        "satisfied_customer": {
            "type": "noul",
            "instructions": "Is the customer happy with the purchase?",
        },
        "delivery_problem": {
            "type": "noul",
            "instructions": "Did the customer experience a delivery problem?",
        },
        "refund_request": {
            "type": "noul",
            "instructions": "Is the customer asking for a refund?",
        },
    },
}

RETURN_POLICY = {
    "model": "jev-latest",
    "state": {
        "return_policy": (
            "Unused items may be returned within 30 days. "
            "Items marked final sale cannot be returned, even within 30 days."
        ),
        "item": "Winter jacket",
        "days_since_purchase": 14,
        "condition": "Unused, tags attached",
        "final_sale": True,
    },
    "questions": {
        "within_return_window": {
            "type": "noul",
            "instructions": "Was the jacket purchased within the last 30 days?",
        },
        "return_eligible": {
            "type": "noul",
            "instructions": "Under the stated return policy, can this jacket be returned?",
        },
        "final_sale_exception": {
            "type": "noul",
            "instructions": "Does the final-sale exclusion apply to this jacket?",
        },
    },
}

EMAIL_TRIAGE = {
    "model": "jev-latest",
    "state": {
        "from": "Alex, Product team",
        "subject": "Roadmap review for Friday",
        "body": (
            "I've attached the draft roadmap for next quarter. Please review it "
            "and leave your comments before our meeting on Friday. "
            "Nothing needs to be done today. This is for internal discussion only."
        ),
    },
    "questions": {
        "action_requested": {
            "type": "noul",
            "instructions": "Does the sender ask the recipient to do something?",
        },
        "urgent_today": {
            "type": "noul",
            "instructions": "Does this email require action today?",
        },
        "customer_complaint": {
            "type": "noul",
            "instructions": "Is this email a complaint from a customer?",
        },
    },
}

BUG_REPORT = {
    "model": "jev-latest",
    "state": {
        "app": "Notes desktop app",
        "report": (
            "The app crashes every time I export a notebook as a PDF. "
            "I've reproduced it three times. All my notes are still saved "
            "and I can reopen them. Exporting as plain text works."
        ),
    },
    "questions": {
        "reproducible_bug": {
            "type": "noul",
            "instructions": "Has the user reproduced the crash more than once?",
        },
        "data_loss": {
            "type": "noul",
            "instructions": "Has the user lost any saved notes?",
        },
        "workaround_available": {
            "type": "noul",
            "instructions": "Can the user export the notes in another format?",
        },
    },
}


if __name__ == "__main__":

    result = ask_jev(CONVERSATION_HISTORY)

    print(json.dumps(result, indent=2))
