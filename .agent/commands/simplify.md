Simplify and refactor $ARGUMENTS.

## Simplification Principles

1. **Single Responsibility** - 1 function = 1 thing
2. **Short Functions** - Target under 20 lines
3. **Shallow Nesting** - Early return, depth ≤ 2
4. **Clear Naming** - Clear enough to not need comments
5. **Type Hints Required** - On all functions

## Steps

1. Identify libraries used in target code
2. Check constraints in `.claude/docs/libraries/`
3. Execute refactoring
4. Verify with tests

## Notes

- Always preserve library features/constraints
- Web search for unclear points
- Don't change behavior (refactoring only)
