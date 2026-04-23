page 50300 "SP Docs Setup"
{
    Caption = 'SharePoint Docs Setup';
    PageType = Card;
    SourceTable = "SP Docs Setup";
    UsageCategory = Administration;
    ApplicationArea = All;

    layout
    {
        area(Content)
        {
            group(General)
            {
                field("Tenant Id"; Rec."Tenant Id")
                {
                    ApplicationArea = All;
                }
                field("Client Id"; Rec."Client Id")
                {
                    ApplicationArea = All;
                }
                field("Client Secret"; Rec."Client Secret")
                {
                    ApplicationArea = All;
                }
                field("Site Id"; Rec."Site Id")
                {
                    ApplicationArea = All;
                }
                field("Drive Id"; Rec."Drive Id")
                {
                    ApplicationArea = All;
                }
                field("Folder Path"; Rec."Folder Path")
                {
                    ApplicationArea = All;
                }
                field("Enabled"; Rec."Enabled")
                {
                    ApplicationArea = All;
                }
            }
        }
    }

    trigger OnOpenPage()
    begin
        if not Rec.Get('DEFAULT') then begin
            Rec.Init();
            Rec."Primary Key" := 'DEFAULT';
            Rec.Insert();
        end;
    end;
}
