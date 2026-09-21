# Third-party notices

## Agent chat Markdown rendering

The desktop agent/chat transcript renderer uses the ReactMarkdown + remark-gfm approach and adapts the copy-button state/timing logic from `useCopyToClipboard` / `CodeHeader` in [Agent Chat UI markdown-text.tsx](https://github.com/langchain-ai/agent-chat-ui/blob/41926d89c9798cebe45a26886d6e437acc5201c1/src/components/thread/markdown-text.tsx), revision `41926d89c9798cebe45a26886d6e437acc5201c1`. Local styling, safe links, reasoning/tool display, clipboard failure handling and timer cleanup are project-specific. No upstream provider/application is imported; raw HTML is not enabled.

- Agent Chat UI is MIT licensed: https://github.com/langchain-ai/agent-chat-ui/blob/main/LICENSE
- `react-markdown` is MIT licensed: https://github.com/remarkjs/react-markdown/blob/main/license
- `remark-gfm` is MIT licensed: https://github.com/remarkjs/remark-gfm/blob/main/license

Agent Chat UI license for the adapted presentation code:

MIT License

Copyright (c) 2025 Brace Sproul

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
