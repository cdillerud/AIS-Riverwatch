codeunit 50300 "SP Docs Mgt"
{
    procedure UploadDocument(SourceRecordId: RecordId; FileName: Text; var InS: InStream)
    var
        Setup: Record "SP Docs Setup";
        DocEntry: Record "SP Document Entry";
        TargetPath: Text;
        AccessToken: Text;
        UploadedItemId: Text;
        UploadedWebUrl: Text;
    begin
        EnsureSetup(Setup);
        AccessToken := GetGraphToken(Setup);

        TargetPath := BuildTargetPath(Setup, FileName);

        UploadToSharePoint(Setup, AccessToken, TargetPath, InS, UploadedItemId, UploadedWebUrl);

        DocEntry.Init();
        DocEntry."Source Table Id" := SourceRecordId.TableNo;
        DocEntry."Source Record Id" := SourceRecordId;
        DocEntry."Document Name" := FileName;
        DocEntry."SharePoint Item Id" := UploadedItemId;
        DocEntry."SharePoint Web Url" := UploadedWebUrl;
        DocEntry."Created At" := CurrentDateTime;
        DocEntry."Created By" := UserId;
        DocEntry.Insert(true);
    end;

    local procedure EnsureSetup(var Setup: Record "SP Docs Setup")
    begin
        if not Setup.Get('DEFAULT') then
            Error('SharePoint Docs Setup has not been created yet.');

        if not Setup.Enabled then
            Error('SharePoint Docs integration is disabled.');

        if (Setup."Tenant Id" = '') or (Setup."Client Id" = '') or (Setup."Client Secret" = '') then
            Error('Tenant Id, Client Id, and Client Secret must be configured.');

        if (Setup."Site Id" = '') or (Setup."Drive Id" = '') then
            Error('Site Id and Drive Id must be configured.');
    end;

    local procedure BuildTargetPath(Setup: Record "SP Docs Setup"; FileName: Text): Text
    begin
        if Setup."Folder Path" = '' then
            exit(FileName);

        exit(Setup."Folder Path" + '/' + FileName);
    end;

    local procedure GetGraphToken(Setup: Record "SP Docs Setup"): Text
    var
        Client: HttpClient;
        Content: HttpContent;
        Headers: HttpHeaders;
        Response: HttpResponseMessage;
        TokenJson: JsonObject;
        AccessTokenJson: JsonToken;
        Body: Text;
    begin
        Body :=
            'grant_type=client_credentials' +
            '&client_id=' + Setup."Client Id" +
            '&client_secret=' + Setup."Client Secret" +
            '&scope=https%3A%2F%2Fgraph.microsoft.com%2F.default';

        Content.WriteFrom(Body);
        Content.GetHeaders(Headers);
        Headers.Clear();
        Headers.Add('Content-Type', 'application/x-www-form-urlencoded');

        Client.Post('https://login.microsoftonline.com/' + Setup."Tenant Id" + '/oauth2/v2.0/token', Content, Response);
        if not Response.IsSuccessStatusCode() then
            Error('Unable to get OAuth token from Azure AD. Status code: %1', Response.HttpStatusCode());

        Response.Content().ReadAs(Body);
        if not TokenJson.ReadFrom(Body) then
            Error('Unable to parse token response.');

        if not TokenJson.Get('access_token', AccessTokenJson) then
            Error('access_token is missing in token response.');

        exit(AccessTokenJson.AsValue().AsText());
    end;

    local procedure UploadToSharePoint(Setup: Record "SP Docs Setup"; AccessToken: Text; TargetPath: Text; FileInStream: InStream; var ItemId: Text; var WebUrl: Text)
    var
        Client: HttpClient;
        Request: HttpRequestMessage;
        Content: HttpContent;
        Headers: HttpHeaders;
        Response: HttpResponseMessage;
        RespBody: Text;
        RespJson: JsonObject;
        IdToken: JsonToken;
        UrlToken: JsonToken;
        Endpoint: Text;
    begin
        Endpoint :=
            'https://graph.microsoft.com/v1.0/sites/' + Setup."Site Id" +
            '/drives/' + Setup."Drive Id" + '/root:/' + TargetPath + ':/content';

        Content.WriteFrom(FileInStream);
        Content.GetHeaders(Headers);
        Headers.Clear();
        Headers.Add('Content-Type', 'application/octet-stream');

        Request.SetRequestUri(Endpoint);
        Request.Method('PUT');
        Request.Content(Content);
        Request.GetHeaders(Headers);
        Headers.Add('Authorization', 'Bearer ' + AccessToken);

        Client.Send(Request, Response);
        if not Response.IsSuccessStatusCode() then
            Error('SharePoint upload failed. Status code: %1', Response.HttpStatusCode());

        Response.Content().ReadAs(RespBody);
        if not RespJson.ReadFrom(RespBody) then
            Error('Unable to parse upload response JSON.');

        if RespJson.Get('id', IdToken) then
            ItemId := IdToken.AsValue().AsText();

        if RespJson.Get('webUrl', UrlToken) then
            WebUrl := UrlToken.AsValue().AsText();
    end;
}
