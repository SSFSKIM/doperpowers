The grill asks in batched rounds, not one question at a time — this is the method for every grill, interactive or dispatched.

Interview your human partner relentlessly until you reach a shared understanding. Map this as a design tree: every decision branches into the decisions that hang off it.

Work the tree in rounds. The frontier is every decision whose prerequisites are already settled — the questions you can ask now without guessing at answers you haven't heard yet. Ask the whole frontier in one round, your recommended answer riding with each question. Deliver by fit: clear multiple-choice questions ride AskUserQuestion, several at once; relatively open but still bounded questions go as numbered prose in the chat (in a non-interactive context — a board ticket, a relay comment — the whole round is one numbered message). Then wait for the answers before the next round.

Each round the answers reshape the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a later round, not this one.

Finding facts is your job, never your human partner's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The decisions are your human partner's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until your human partner confirms you have reached a shared understanding.
