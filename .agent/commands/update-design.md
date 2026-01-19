Record/update project design and implementation decisions in `.claude/docs/DESIGN.md` based on conversation content.

Note: This command explicitly invokes the same workflow as the `design-tracker` skill.
Use this when you want to force a design document update.

## Workflow

1. Read existing `.claude/docs/DESIGN.md`
2. Extract decisions/information from the conversation
3. Update the appropriate section
4. Add entry to Changelog with today's date

## Sections

| Topic | Section |
|-------|---------|
| Goals, purpose | Overview |
| Structure, components | Architecture |
| Design patterns | Implementation Plan > Patterns |
| Library choices | Implementation Plan > Libraries |
| Decision rationale | Implementation Plan > Key Decisions |
| Future work | TODO |
| Unresolved issues | Open Questions |

## Language

- Document content: English (technical), Japanese OK for descriptions
- User communication: Japanese

If $ARGUMENTS provided, focus on recording that content.
