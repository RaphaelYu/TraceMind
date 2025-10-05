# Quickstart

## Install
- `pip install -e .[yaml,prom]`

## Create a Demo Project
- `tm init demo --template minimal`
- `cd demo`
- `tm run flows/hello.yaml -i '{"name":"world"}'`

## Optional: Validate Data Cleanup Example
- `tm -c examples/validation.toml run examples/agents/data_cleanup/flows/data_cleanup.yaml -i '{"input_file":"examples/agents/data_cleanup/data/sample-small.csv"}' --direct`

## Next Steps
- Review the [Plugin SDK](docs/plugins.md)
