# Diagnostic Routing

Select exactly one initial diagnostic environment from the user's answer.

| User answer | Allowed initial sources | Prohibited initial sources |
| --- | --- | --- |
| Local | Current terminal output; files under the repository's local `runs/` directory; log files named by the applicable local launcher skill; logs from locally running Docker containers or processes | SSH, remote server files, remote Docker, remote journald |
| `jurisdigta-server` | Bounded read-only queries through `ssh -o BatchMode=yes jurisdigta-server`; relevant remote Docker logs; relevant journald unit; relevant file under `/srv/jurisdigta/runs/logs/` | Unrelated local application logs; secret files; database/user content |

## Local path

1. Identify the affected locally running component and how it was started.
2. Prefer the terminal or log path printed by its repository launcher.
3. Query only the relevant local file, process, or container and the reported time window.
4. Do not start, stop, restart, reconfigure, or clear a service merely to obtain logs unless the user separately authorizes that action.
5. If expected local logs do not exist, report that fact and ask how the component was launched rather than switching to the server.

## `jurisdigta-server` path

1. Explain the intended service, time window, and maximum output, then obtain permission for remote log access.
2. Verify SSH reachability with a read-only bounded check.
3. Query only the relevant source:
   - `docker logs --since <time> --tail <limit> <container>`;
   - `journalctl -u <unit> --since <time> -n <limit> --no-pager`;
   - `tail -n <limit> /srv/jurisdigta/runs/logs/<relevant-file>.log`.
4. Do not use broad recursive searches or read `/srv/jurisdigta/secrets/`.
5. If the affected service is unclear, list only service/container names first and ask the user before retrieving content.

## Scope expansion

Inspect both environments only when:

- the evidence indicates a local client calling the remote server;
- the user confirms both sides are in scope; and
- each source remains independently minimized and sanitized.

Record the selected environment and actual log source in the GitHub issue.
