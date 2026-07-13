import os
from dotenv import load_dotenv
from azure.identity import EnvironmentCredential
from azure.keyvault.certificates import CertificateClient, CertificatePolicy

load_dotenv()

def test_key_vault():
    # 1. Grab the Vault URL from the environment
    key_vault_url = os.environ.get("AZURE_KEYVAULT_URL")
    if not key_vault_url:
        print("Error: AZURE_KEYVAULT_URL environment variable is missing.")
        return

    print(f"Connecting to: {key_vault_url}")

    # 2. Authenticate using the AZURE_* environment variables
    # This automatically picks up your Tenant ID, Client ID, and Secret
    credential = EnvironmentCredential()

    # 3. Create the Certificate Client
    client = CertificateClient(vault_url=key_vault_url, credential=credential)

    cert_name = "test-cert-01"

    try:
        # 4. Test WRITE privileges (The "Officer" role)
        print(f"\nAttempting to create a self-signed certificate named '{cert_name}'...")
        # Get the default policy for a standard self-signed cert
        policy = CertificatePolicy.get_default()
        
        # Begin the creation process (it runs asynchronously in Azure)
        poller = client.begin_create_certificate(certificate_name=cert_name, policy=policy)
        certificate = poller.result()
        print("✅ Success! Write permissions are fully working.")

        # 5. Test READ privileges (Get/List)
        print("\nListing all certificates in the vault:")
        certificates = client.list_properties_of_certificates()
        
        for cert in certificates:
            print(f" 📄 {cert.name} (Enabled: {cert.enabled})")

    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        print("If you see 'Authorization failed', remember RBAC takes ~5 mins to propagate!")

if __name__ == "__main__":
    test_key_vault()