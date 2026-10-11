"""No-cost OpenCode control: local scripted provider replies without tools."""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        base = dict(id='local-control', model='noop', created=1)
        if request.get('stream'):
            chunks = [dict(**base, object='chat.completion.chunk', choices=[
                dict(index=0, delta={'role': 'assistant', 'content': 'READY'}, finish_reason=None)]),
                dict(**base, object='chat.completion.chunk', choices=[
                    dict(index=0, delta={}, finish_reason='stop')],
                    usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2})]
            body = ''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
            kind = 'text/event-stream'
        else:
            body = json.dumps(dict(**base, object='chat.completion', choices=[
                dict(index=0, message={'role': 'assistant', 'content': 'READY'}, finish_reason='stop')],
                usage={'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}))
            kind = 'application/json'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = {'snapshot': os.environ.get('REFERENCE_MUTANT') == 'harness-default',
        'provider': {'calibration': {'npm': '@ai-sdk/openai-compatible',
            'options': {'baseURL': f'http://127.0.0.1:{server.server_port}/v1'},
            'models': {'noop': {'name': 'noop', 'limit': {'context': 128000, 'output': 1024}}}}}}
    env = dict(os.environ, OPENCODE_CONFIG_CONTENT=json.dumps(config),
               OPENCODE_DISABLE_MODELS_FETCH='true', OPENCODE_DISABLE_AUTOUPDATE='true',
               OPENCODE_DISABLE_FFF='false' if os.environ.get('REFERENCE_MUTANT')=='harness-default' else 'true')
    try:
        result = subprocess.run(['opencode', 'run', '-m', 'calibration/noop', '--pure', '--auto',
            '--format', 'json', '--dir', '/workspace', 'Reply READY. Do not call tools or read files.'],
            env=env, timeout=90, capture_output=True, text=True)
        print(result.stdout)
        if result.returncode or 'step_finish' not in result.stdout:
            raise RuntimeError('local harness probe failed: '+result.stderr[-1000:])
        if '"type":"tool_use"' in result.stdout.replace(' ', ''):
            raise RuntimeError('probe unexpectedly called a tool')
    finally:
        server.shutdown()


if __name__ == '__main__':
    main()
