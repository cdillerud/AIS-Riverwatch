# SharePoint Document Linker (Business Central Extension)

This folder contains a starter Microsoft Dynamics 365 Business Central AL extension intended to replace the core document storage behavior typically handled by third-party document add-ons by storing files in SharePoint and metadata in Business Central.

## What is implemented

- Setup table + setup page for SharePoint / Azure app registration values.
- Document metadata table for links between BC records and SharePoint files.
- List page to browse uploaded documents and open in SharePoint.
- Management codeunit that:
  - gets an Azure AD OAuth token (client credentials flow),
  - uploads a file to SharePoint via Microsoft Graph,
  - stores metadata locally in BC.

## Current limitations (important)

This is a production-oriented scaffold, not a full Zeta Docs feature-for-feature replacement yet.

Still needed for parity:

1. Document capture from pages (Sales, Purchase, Posted Docs, etc.)
2. FactBoxes and context actions on standard BC pages
3. Download/versioning/check-in/check-out behaviors
4. Retention policy and permission model mapping
5. Upgrade codeunits and data migration from existing document providers
6. Test codeunits and automated CI packaging

## Credentials and security

Do **not** store production secrets in plain text fields long-term.

Minimum for a secure deployment:

- Move client secret handling to a secret store approach supported in your environment.
- Restrict Graph permissions to the specific SharePoint site/drive.
- Use a dedicated Azure App Registration with certificate-based auth where possible.
- Add auditing/telemetry for uploads/downloads/deletes.

## Suggested next step

If you share:

- tenant ID,
- app registration client ID,
- preferred auth pattern (secret vs certificate),
- SharePoint site/drive details,
- and target BC pages/documents to support first,

I can implement the next iteration to attach this directly to specific Business Central records and workflows.

## Purchase Invoice focus (current iteration)

This iteration adds actions directly on the **Purchase Invoice** page:

- **Upload to SharePoint**: prompts user for a local file and uploads to SharePoint.
- **View SharePoint Documents**: opens the metadata list filtered to the current purchase invoice.

Notes:

- The purchase invoice record must exist (saved) before upload.
- Upload now sends binary stream content (`application/octet-stream`) so PDFs and attachments are supported.
