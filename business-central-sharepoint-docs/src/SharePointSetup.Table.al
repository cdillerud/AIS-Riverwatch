table 50300 "SP Docs Setup"
{
    Caption = 'SP Docs Setup';
    DataClassification = SystemMetadata;

    fields
    {
        field(1; "Primary Key"; Code[10])
        {
            Caption = 'Primary Key';
        }
        field(10; "Tenant Id"; Text[100])
        {
            Caption = 'Azure Tenant Id';
            DataClassification = SystemMetadata;
        }
        field(20; "Client Id"; Text[100])
        {
            Caption = 'Azure App Client Id';
            DataClassification = SystemMetadata;
        }
        field(30; "Client Secret"; Text[250])
        {
            Caption = 'Azure App Client Secret';
            DataClassification = SensitivePersonalData;
            ExtendedDatatype = Masked;
        }
        field(40; "Site Id"; Text[150])
        {
            Caption = 'SharePoint Site Id';
            DataClassification = CustomerContent;
        }
        field(50; "Drive Id"; Text[150])
        {
            Caption = 'SharePoint Drive Id';
            DataClassification = CustomerContent;
        }
        field(60; "Folder Path"; Text[250])
        {
            Caption = 'Default Folder Path';
            DataClassification = CustomerContent;
        }
        field(70; "Enabled"; Boolean)
        {
            Caption = 'Enabled';
        }
    }

    keys
    {
        key(PK; "Primary Key")
        {
            Clustered = true;
        }
    }
}
