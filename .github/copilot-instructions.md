# AI Jurisdiction Agents - Copilot Instructions

## Project Overview
This project implements AI agents that simulate legal professionals (lawyers, judges, mediators) for automated jurisdiction and legal decision-making processes. The agents are designed to handle case analysis, argument presentation, and dispute resolution in a simulated legal environment.

## Architecture
- **Agent Roles**: Separate modules/classes for LawyerAgent, JudgeAgent, MediatorAgent
- **Communication**: Agents interact via a message-passing system or API endpoints
- **Data Flow**: Cases flow from intake → lawyer analysis → mediation → judicial decision
- **Decision Logic**: Rule-based systems combined with AI/ML for nuanced legal reasoning
- **Orchestration**: Planned with .NET Aspire for service discovery, health checks, and distributed tracing (integration details TBD)

## Key Patterns
- **Agent Base Class**: All agents inherit from a common `BaseAgent` class with shared methods for logging, state management, and communication
- **Case Representation**: Use `Case` dataclass with fields for parties, claims, evidence, and status
- **Async Operations**: Agent interactions use async/await for non-blocking legal consultations
- **Logging**: Comprehensive logging of all decisions and reasoning steps for audit trails

## Development Workflow
- **Environment**: Python 3.9+ with virtualenv, .NET 8+ with Aspire
- **Dependencies**: Python packages via `pip install -r requirements.txt`, .NET packages via NuGet
- **Testing**: `pytest` for Python unit/integration tests, xUnit for C# tests
- **Linting**: `black` and `flake8` for Python, StyleCop for C# code style
- **Agent Execution**: Run individual agents with `python -m agents.lawyer_agent --case-id <id>` (orchestration via .NET Aspire TBD)
- **Build**: Use `dotnet build` for .NET components, ensure Python environments are configured

## Conventions
- **Python Naming**: Use descriptive names like `analyze_case()`, `render_judgment()`
- **C# Naming**: PascalCase for classes/methods (e.g., `AnalyzeCase()`, `RenderJudgment()`), camelCase for variables
- **Error Handling**: Raise custom `LegalException` in Python, throw `LegalException` in C#
- **Documentation**: Docstrings in Python, XML comments in C# for all public methods, especially decision logic
- **Versioning**: Semantic versioning for agent capabilities and legal rule updates

## Integration Points
- **External APIs**: Potential integration with legal databases or court APIs
- **Persistence**: Use SQLite/PostgreSQL for case storage and agent state
- **Monitoring**: Integrate with logging services for agent performance metrics

## Key Files
- `agents/base_agent.py`: Core agent functionality (Python)
- `models/case.py`: Case data structures (Python)
- `services/mediation_service.py`: Cross-agent communication (Python)
- `tests/test_agents.py`: Agent behavior tests (Python)
- `AppHost/Program.cs`: .NET Aspire orchestration entry point (planned)
- `ServiceDefaults/Extensions.cs`: Shared service configurations (planned)
- `AgentService/Program.cs`: C# service for agent management (planned)