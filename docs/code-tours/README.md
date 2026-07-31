# Code Tours

These tours are short orientation maps for humans and agents. Read the relevant
tour before changing a flow, then update it when the flow or its verification
path changes.

Start with:

- `generated-app-flows.md` - core Django SaaS flows, entrypoints, files to
  inspect, checks, and common mistakes.

Add new tours when a feature grows enough that future contributors would
otherwise rediscover the same routing, service, task, or permission structure.
Good tours name:

- Entry points.
- Core behavior kernel.
- Persistence or side effects.
- Tests.
- Quality commands.
- Common footguns.
