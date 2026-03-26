sequenceDiagram
    autonumber
    participant User as User (index.html)
    participant App as app.py (Flask)
    participant Comp as composer.py (Generator)
    participant Zip as Zip Utility

    Note over User, App: Phase 1: User Request
    User->>App: POST /generate (Form Data)
    Note right of User: Stack, Image, Port, Volumes, Env

    Note over App, Comp: Phase 2: String Generation
    App->>Comp: generate_dockerfile(image, port)
    Comp-->>App: returns Dockerfile string

    App->>Comp: generate_compose(svc, port, env, volumes)
    Comp->>Comp: format_env_vars(env)
    
    rect rgb(255, 223, 186)
    Note right of Comp: Task 1 Fix: Volume Mapping Order
    Comp->>Comp: format_volumes(volumes)
    end
    
    Comp-->>App: returns docker-compose.yml string

    Note over App, Zip: Phase 3: Packaging
    App->>Zip: Add Dockerfile + docker-compose.yml
    App->>Zip: Add entrypoint.sh (Task 1 Fix: chmod +x)
    Zip-->>App: project.zip (Binary)

    Note over App, User: Phase 4: Delivery
    App-->>User: Send ZIP file to Browser
