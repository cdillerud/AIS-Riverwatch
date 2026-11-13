table 50301 "SP Document Entry"
{
    Caption = 'SP Document Entry';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Entry No."; Integer)
        {
            Caption = 'Entry No.';
            AutoIncrement = true;
        }
        field(10; "Source Table Id"; Integer)
        {
            Caption = 'Source Table Id';
        }
        field(20; "Source Record Id"; RecordId)
        {
            Caption = 'Source Record Id';
        }
        field(30; "Document Name"; Text[250])
        {
            Caption = 'Document Name';
        }
        field(40; "SharePoint Item Id"; Text[150])
        {
            Caption = 'SharePoint Item Id';
        }
        field(50; "SharePoint Web Url"; Text[250])
        {
            Caption = 'SharePoint Web Url';
        }
        field(60; "Created At"; DateTime)
        {
            Caption = 'Created At';
        }
        field(70; "Created By"; Code[50])
        {
            Caption = 'Created By';
        }
    }

    keys
    {
        key(PK; "Entry No.")
        {
            Clustered = true;
        }

        key(SourceRef; "Source Table Id", "Source Record Id")
        {
        }
    }
}
