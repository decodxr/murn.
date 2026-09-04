# ComfyUI workflows

murn. drives ComfyUI through its local HTTP API.

## Create the txt2img workflow

1. Open ComfyUI and build a txt2img workflow that already generates correctly.
2. Export/save the workflow in **API format**. The regular UI workflow JSON is not the same format used by `POST /prompt`.
3. Save the API-format file here as `txt2img_api.json`.
4. Open that JSON and identify the node IDs for:
   - positive prompt text node
   - negative prompt text node (optional)
   - sampler/seed node (optional)
   - latent image width/height node (optional)
5. Put those IDs in `.env`:

```env
MURN_COMFY_POSITIVE_NODE=6
MURN_COMFY_NEGATIVE_NODE=7
MURN_COMFY_SEED_NODE=3
MURN_COMFY_LATENT_NODE=5
```

The numbers above are examples only. Use the IDs from your workflow.

## Why the workflow is not committed

Image models and custom-node graphs vary a lot. murn. keeps the adapter generic and ignores
`workflows/txt2img_api.json` in Git so your local workflow can change without polluting the repo.
