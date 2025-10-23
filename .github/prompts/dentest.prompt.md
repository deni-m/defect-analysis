---
mode: 'agent'
model: GPT-5
tools: ['runNotebooks', 'search/codebase', 'runCommands', 'githubRepo']
description: 'Generate a new React form component'
---
Your goal is to generate a new React form component based on the templates in #githubRepo contoso/react-templates.

Ask for the form name and fields if not provided.

Requirements for the form:
* Use form design system components: [design-system/Form.md](../docs/design-system/Form.md)