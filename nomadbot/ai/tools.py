"""Tool schemas offered to the AI on the owner's DM channel.

These are the only actions the founder's natural-language commands can turn
into — the model picks one (or none, if it should just reply in text) and
supplies arguments; nomadbot/handlers/owner.py dispatches the result to
nomadbot/actions.py or nomadbot/scheduler.py. Keeping the schema list short and
explicit is deliberate: the model can only do what's listed here, nothing
implicit or improvised.
"""

DESTINATION_NAMES_PLACEHOLDER = "one of the configured destination keys — call list_destinations first if unsure"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Post a message to one of the community's groups right now.",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": DESTINATION_NAMES_PLACEHOLDER},
                    "text": {"type": "string", "description": "The message to post."},
                },
                "required": ["destination", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dm_member",
            "description": (
                "Send a direct message to one specific community member, by "
                "@username or numeric id. Only works if the bot has seen that "
                "person post or join in one of its groups before — there is no "
                "way to DM someone Telegram has never let the bot see."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "description": "@username or numeric id"},
                    "text": {"type": "string", "description": "The message to send them."},
                },
                "required": ["identifier", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_task",
            "description": (
                "Schedule a send_message or dm_member action to run later, once "
                "or on a recurring cron schedule. Use this for anything with a "
                "time attached — 'every Wednesday at 9am', 'tomorrow at noon', "
                "'send this weekly'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cron_expr": {
                        "type": "string",
                        "description": (
                            "Standard 5-field cron expression in the server's "
                            "local time, e.g. '0 9 * * 3' for every Wednesday "
                            "9am. Omit for a one-off task."
                        ),
                    },
                    "run_at_unix_ts": {
                        "type": "integer",
                        "description": "Unix timestamp for a one-off task. Required if cron_expr is omitted.",
                    },
                    "action_type": {
                        "type": "string",
                        "enum": ["send_message", "dm_member"],
                    },
                    "action_payload": {
                        "type": "object",
                        "description": (
                            "The arguments that action_type needs: {destination, "
                            "text} for send_message, {identifier, text} for dm_member."
                        ),
                    },
                },
                "required": ["action_type", "action_payload"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_scheduled_tasks",
            "description": "List your currently active scheduled tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_scheduled_task",
            "description": "Cancel one of your scheduled tasks by its id.",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "integer"}},
                "required": ["job_id"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are the Nomad Network's Telegram bot, talking privately with its "
    "founder. You may call exactly one tool per message if the founder is "
    "asking you to do something (post somewhere, message someone, schedule "
    "something). If they are just chatting or asking a question with no "
    "action to take, reply in plain text and do not call a tool. Never invent "
    "a destination name that was not given to you — if you are unsure which "
    "destination they mean, ask in plain text instead of guessing."
)
