# First-Move Agent Gesture Example

This tiny example is safe to run from a fresh clone. It does not read private
history, registry data, environment variables, credentials, or external APIs.

From the repository root:

```sh
python examples/first-move-agent-gesture/agent_first_move_demo.py --json
```

The output is a source-backed first move for a new agent: it names public source
refs to open before broad searching and keeps private/local machine paths out of
the payload.
