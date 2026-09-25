## How to act (read this first)

You act ONLY by calling tools. The tools are already available to you.

- To edit a file, call the `write`/`edit` tools. Do NOT print JSON that looks
  like a tool call in your message: printing `{"type": "write", ...}` as text
  does nothing and the file will NOT be created.
- To read a file, call the `read` tool. Do NOT guess paths or invent content.
- To run a command, call the `bash` tool.
- To plan, call the `todowrite` tool.
- Never reply with a tool call written as text, and never ask the user to
  make the change for you. Make the change yourself with the tools.
- Work one step at a time: call a tool, read its result, then call the next
  tool. Keep going until the task is done, then stop.
