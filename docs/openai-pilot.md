# OpenAI Reactive Pilot

This workflow runs the frozen Reactive LLM Baseline pilot with three current
OpenAI API models:

- gpt-5.6-sol
- gpt-5.6-terra
- gpt-5.6-luna

The workflow passes them to LiteLLM as:

- openai/gpt-5.6-sol
- openai/gpt-5.6-terra
- openai/gpt-5.6-luna

## Secret setup

The workflow never stores an API key in the repository.

In GitHub:

1. Open repository Settings.
2. Open Secrets and variables -> Actions.
3. Add a repository secret named OPENAI_API_KEY.
4. Use an active OpenAI API project key.

## Run

Open Actions -> OpenAI Reactive Pilot -> Run workflow.

The workflow executes:

3 models x 5 episodes x 3 repeats = 45 episode runs.

Each workflow invocation writes to a run-specific output directory using the
GitHub run ID and attempt number, so reruns do not overwrite prior evidence.

## Output

The uploaded artifact contains:

- every raw replicate JSON;
- runs.csv;
- summary.json.

The artifact is retained for 30 days. The repository remains unchanged by the
experiment run.
