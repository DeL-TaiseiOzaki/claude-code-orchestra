# Task Patterns Reference

Common patterns for creating effective task lists.

## Task Granularity

### Too Coarse (Bad)
```
- Implement authentication system
```

### Too Fine (Bad)
```
- Create User class
- Add email field to User class
- Add password field to User class
- Add validation for email field
```

### Just Right (Good)
```
- Create User model with email and password fields
- Implement password hashing and validation
- Create login endpoint with JWT token generation
- Add authentication middleware
- Write tests for auth flow
```

## Task Categories

### 1. Setup/Preparation
Tasks that prepare the environment or scaffolding:
- Install dependencies
- Create directory structure
- Set up configuration files
- Create base classes/interfaces

### 2. Core Implementation
Main feature development:
- Implement business logic
- Create data models
- Build API endpoints
- Develop UI components

### 3. Integration
Connecting components:
- Wire up dependencies
- Connect to external services
- Integrate with existing features

### 4. Testing
Verification tasks:
- Write unit tests
- Add integration tests
- Manual testing checklist

### 5. Documentation (Optional)
Only when explicitly needed:
- Update API docs
- Add code comments for complex logic

## Dependency Ordering

Order tasks by dependencies:

```
1. [Independent] Create database schema
2. [Independent] Define TypeScript interfaces
3. [Depends on 1,2] Implement data access layer
4. [Depends on 3] Build service layer
5. [Depends on 4] Create API endpoints
6. [Depends on 5] Add authentication checks
```

## Task Status Flow

```
pending → in_progress → completed
                ↓
         (if blocked)
                ↓
        Create new task for blocker
```

## Example: User Authentication Feature

```
## Setup
- [ ] Add bcrypt and jsonwebtoken dependencies
- [ ] Create auth/ directory structure

## Core Implementation
- [ ] Create User model with password hashing
- [ ] Implement UserRepository with CRUD operations
- [ ] Create AuthService with login/register logic
- [ ] Build POST /auth/register endpoint
- [ ] Build POST /auth/login endpoint
- [ ] Implement JWT middleware for protected routes

## Integration
- [ ] Add auth middleware to existing protected routes
- [ ] Update user creation flow to use new auth

## Testing
- [ ] Write unit tests for AuthService
- [ ] Write integration tests for auth endpoints
- [ ] Test token refresh flow
```

## Complexity Estimation

From Codex analysis, tag tasks with complexity:

| Complexity | Time Estimate | Characteristics |
|------------|---------------|-----------------|
| Low | 5-15 min | Single file, clear pattern |
| Medium | 15-30 min | Multiple files, some decisions |
| High | 30-60 min | Complex logic, research needed |

## When to Re-plan

Create new tasks or consult Codex again when:

1. **Unexpected complexity** — Task taking 2x+ estimated time
2. **Blocker discovered** — Dependency on unfinished work
3. **Scope change** — User adds new requirements
4. **Technical pivot** — Chosen approach doesn't work
