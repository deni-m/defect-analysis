import os
from openai import AzureOpenAI

def main():
    key = os.getenv("AZURE_OPENAI_KEY")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    if not key or not endpoint:
        print("Missing AZURE_OPENAI_KEY or AZURE_OPENAI_ENDPOINT env vars")
        return

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-05-01-preview")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    print(f"Using endpoint={endpoint}, api_version={api_version}, deployment={deployment}")

    client = AzureOpenAI(
        api_key=key,
        azure_endpoint=endpoint,
        api_version=api_version,
    )

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": "Return 'pong'"}],
            max_tokens=5,
            temperature=0.0,
        )
        content = resp.choices[0].message.content.strip()
        print("Success. Response:", content)
    except Exception as e:
        print("Chat completion failed:")
        print(f"Type: {type(e).__name__}")
        print(f"Message: {e}")
        print("Troubleshooting suggestions:")
        print("- Verify deployment name matches Azure portal exactly.")
        print("- Try newer API version (e.g. 2024-08-01-preview).")
        print("- Check endpoint format: https://<resource>.openai.azure.com")
        print("- Confirm resource is in correct region and accessible from your network.")

if __name__ == "__main__":
    main()