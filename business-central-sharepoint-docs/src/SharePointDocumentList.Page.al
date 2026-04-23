page 50301 "SP Document Entries"
{
    Caption = 'SharePoint Documents';
    PageType = List;
    SourceTable = "SP Document Entry";
    UsageCategory = Lists;
    ApplicationArea = All;

    layout
    {
        area(Content)
        {
            repeater(Documents)
            {
                field("Entry No."; Rec."Entry No.")
                {
                    ApplicationArea = All;
                }
                field("Document Name"; Rec."Document Name")
                {
                    ApplicationArea = All;
                }
                field("SharePoint Web Url"; Rec."SharePoint Web Url")
                {
                    ApplicationArea = All;
                }
                field("Created At"; Rec."Created At")
                {
                    ApplicationArea = All;
                }
                field("Created By"; Rec."Created By")
                {
                    ApplicationArea = All;
                }
            }
        }
    }

    actions
    {
        area(Processing)
        {
            action(OpenInBrowser)
            {
                Caption = 'Open in SharePoint';
                Image = Navigate;
                ApplicationArea = All;

                trigger OnAction()
                begin
                    if Rec."SharePoint Web Url" = '' then
                        Error('No SharePoint URL available for this document.');
                    Hyperlink(Rec."SharePoint Web Url");
                end;
            }
        }
    }
}
