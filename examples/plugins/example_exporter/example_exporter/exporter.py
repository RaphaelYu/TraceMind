class ExampleExporter:
    def setup(self, config):
        print("setup", flush=True)

    def on_event(self, record):
        print("event", flush=True)

    def flush(self):
        print("flush", flush=True)

    def teardown(self):
        print("teardown", flush=True)
