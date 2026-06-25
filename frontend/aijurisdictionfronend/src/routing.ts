const AGENT_HOSTS = new Set(["agent.jurisdigta.eu"]);

export function isAgentHost(hostname = window.location.hostname): boolean {
  return AGENT_HOSTS.has(hostname.toLowerCase());
}
