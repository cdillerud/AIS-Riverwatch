pageextension 50302 "Purchase Invoice SP Docs" extends "Purchase Invoice"
{
    actions
    {
        addlast(Processing)
        {
            action(SPUploadDocument)
            {
                Caption = 'Upload to SharePoint';
                ApplicationArea = All;
                Image = Attach;
                Promoted = true;
                PromotedCategory = Process;

                trigger OnAction()
                var
                    SPDocsMgt: Codeunit "SP Docs Mgt";
                    FileName: Text;
                    InS: InStream;
                begin
                    if Rec.IsTemporary then
                        Error('The document must be saved before files can be uploaded.');

                    if not UploadIntoStream('Select a file', '', 'All Files (*.*)|*.*', FileName, InS) then
                        exit;

                    SPDocsMgt.UploadDocument(Rec.RecordId, FileName, InS);
                    Message('File %1 uploaded to SharePoint.', FileName);
                end;
            }

            action(SPViewDocuments)
            {
                Caption = 'View SharePoint Documents';
                ApplicationArea = All;
                Image = ViewDetails;
                Promoted = true;
                PromotedCategory = Process;

                trigger OnAction()
                var
                    DocEntry: Record "SP Document Entry";
                begin
                    DocEntry.SetRange("Source Table Id", Database::"Purchase Header");
                    DocEntry.SetRange("Source Record Id", Rec.RecordId);
                    Page.RunModal(Page::"SP Document Entries", DocEntry);
                end;
            }
        }
    }
}
