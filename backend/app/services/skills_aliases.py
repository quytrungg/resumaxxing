"""Surface-form aliases for skill/requirement matching.

Data only: ``ALIASES`` maps a canonical lowercase term to the other ways a CV
(or a job description) might spell it. Matching code lives in
``services/requirements.py``; add entries here when a real miss is reported.

Keep keys lowercase. A canonical term that is also a common English word (go,
react, flask, ...) is listed in ``AMBIGUOUS_SURFACES`` over there and matched
case-sensitively, so prose does not register as a skill.
"""

ALIASES = {
    # Languages
    "javascript": ["js", "es6", "ecmascript"],
    "typescript": ["ts"],
    "python": ["py3", "python3"],
    "java": [],
    "kotlin": [],
    "scala": [],
    "golang": ["go"],
    "rust": [],
    "ruby": [],
    "php": [],
    "c++": ["cpp"],
    "c#": ["csharp"],
    "sql": [],
    # Frameworks / libraries
    "react": ["react.js", "reactjs"],
    "vue": ["vue.js", "vuejs"],
    "angular": ["angularjs"],
    "next.js": ["nextjs"],
    "node.js": ["nodejs"],
    "django": [],
    "flask": [],
    "fastapi": ["fast api"],
    "rails": ["ruby on rails"],
    "spring boot": ["springboot", "spring"],
    ".net": ["dotnet", "asp.net"],
    "graphql": ["graph ql"],
    # Data / storage
    "postgresql": ["postgres", "psql"],
    "mysql": [],
    "mongodb": ["mongo"],
    "redis": [],
    "elasticsearch": ["elastic search"],
    "kafka": ["apache kafka"],
    "rabbitmq": ["rabbit mq"],
    "spark": ["apache spark"],
    "airflow": ["apache airflow"],
    "snowflake": [],
    "dbt": [],
    # Cloud / infra
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": ["microsoft azure"],
    "kubernetes": ["k8s"],
    "docker": ["containerisation", "containerization"],
    "terraform": ["iac", "infrastructure as code"],
    "linux": ["unix"],
    "ci/cd": [
        "ci cd", "cicd", "continuous integration", "continuous delivery",
        "continuous deployment",
    ],
    "github actions": ["gh actions"],
    "observability": ["monitoring", "telemetry"],
    "opentelemetry": ["otel", "open telemetry"],
    "prometheus": [],
    "grafana": [],
    "datadog": [],
    # APIs / architecture
    "rest": ["restful", "rest api", "rest apis", "restful api", "restful apis"],
    "grpc": [],
    "microservices": ["micro services"],
    "event-driven architecture": [
        "event driven architecture", "event-driven", "event driven",
    ],
    "distributed systems": ["distributed system"],
    "system design": ["systems design"],
    "domain-driven design": ["ddd"],
    # Practices / tooling
    "git": ["github", "gitlab"],
    "tdd": ["test driven development", "test-driven development"],
    "agile": ["scrum", "kanban"],
    "jira": [],
    "a/b testing": ["ab testing", "split testing"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "natural language processing": ["nlp"],
    "stakeholder management": ["stakeholder", "stakeholders"],
}
