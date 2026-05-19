# CORE COMMANDS & ARCHITECTURE GUIDELINES

This document serves as the primary guideline for all developers and AI agents working on this FastAPI backend project.

## 1. Project Architecture (Modular Monolith)

We follow a strict layered architecture pattern. Do not mix concerns. 
- **Controllers (Routes)**: Only receive HTTP requests, inject dependencies, call the Service layer, and return responses. No business logic allowed.
- **Service Layer**: Contains 100% of the business logic. Handles validation, auth checks, computations, and orchestration.
- **Repository Layer**: Handles all database interactions (SQLAlchemy queries). Services must call Repositories to get/save data.

## 2. Directory Structure Rules

When creating or modifying features, you MUST place code in the following locations:

### API Routes
- **Location**: `app/api/v1/routes/{module_name}.py`
- **Rule**: All HTTP endpoints (`@router.get`, `@router.post`, etc.) go here. 
- **Registration**: Routes must be included in `app/api/v1/router.py`.
- **Prohibited**: DO NOT place `router.py` files inside `app/modules/`.

### Business Logic & Data
- **Location**: `app/modules/{module_name}/`
- **Files**:
  - `models.py`: SQLAlchemy ORM models.
  - `schemas.py`: Pydantic models for request/response validation.
  - `repository.py`: Database access classes (e.g., `UserRepository`).
  - `service.py`: Business logic classes (e.g., `UserService`).
  - `utils.py` (Optional): Helper functions.

## 3. Authentication & Authorization (RBAC)

- **Auth Module**: All login logic, JWT generation, and `access_contexts` generation are centralized in `app/modules/auth/` and exposed via `app/api/v1/routes/auth.py`.
- **Dependencies**: Use `app.api.deps` for protecting endpoints:
  - `Depends(get_current_user)`: Requires authentication.
  - `Depends(get_optional_current_user)`: Optionally reads the token (for mixed public/private endpoints).
  - `Depends(require_roles([UserRole.SUPERADMIN]))`: Protects endpoint with strict Role-Based Access Control.
- **Access Contexts**: The system uses `access_contexts` to define dynamic data scopes (e.g., scoping data to a specific `company_id` or `gas_station_id`). Rely on this array inside the JWT payload rather than hardcoding global context IDs.

## 4. Database Migrations (Alembic)

When modifying `models.py`, you must track changes using Alembic.
1. Run: `alembic revision --autogenerate -m "description_of_change"`
2. Verify the generated migration file in `migrations/versions/`. (Note: Enum changes might require manual SQL additions).
3. Apply: `alembic upgrade head`

## 5. Pagination Standard

When returning lists of resources, follow the standard pagination format:
- **Request Parameters**: `page: int = 1`, `page_size: int = 20`.
- **Calculations (in Service)**: `skip = (page - 1) * page_size`, `limit = page_size`.
- **Response Format**:
  ```json
  {
    "items": [...data],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 100,
      "total_pages": 5
    }
  }
  ```

## 6. General Best Practices
- Never use print statements for debugging in production; use standard logging.
- Always use asynchronous SQLAlchemy queries (`execute`, `scalars().all()`).
- Use explicit Pydantic schemas for responses (`response_model`).
