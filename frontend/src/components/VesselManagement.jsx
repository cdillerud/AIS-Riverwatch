import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { 
  Ship, Plus, Trash2, Star, Loader2, AlertCircle
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

export default function VesselManagement() {
  const { user, addVessel, removeVessel, setPrimaryVessel, refreshUser } = useAuth();
  const [newMmsi, setNewMmsi] = useState("");
  const [newBoatName, setNewBoatName] = useState("");
  const [adding, setAdding] = useState(false);
  const [removingMmsi, setRemovingMmsi] = useState(null);
  const [settingPrimary, setSettingPrimary] = useState(null);

  const vessels = user?.vessels || [];

  const handleAddVessel = async (e) => {
    e.preventDefault();
    
    if (!newMmsi.trim()) {
      toast.error("Please enter an MMSI");
      return;
    }
    
    // Validate MMSI format (should be 9 digits)
    if (!/^\d{9}$/.test(newMmsi.trim())) {
      toast.error("MMSI must be exactly 9 digits");
      return;
    }

    setAdding(true);
    try {
      await addVessel(newMmsi.trim(), newBoatName.trim(), vessels.length === 0);
      toast.success(`Added vessel ${newBoatName || newMmsi}`);
      setNewMmsi("");
      setNewBoatName("");
    } catch (err) {
      toast.error(err.message || "Failed to add vessel");
    } finally {
      setAdding(false);
    }
  };

  const handleRemoveVessel = async (mmsi, boatName) => {
    if (!confirm(`Remove ${boatName || mmsi} from your fleet?`)) return;
    
    setRemovingMmsi(mmsi);
    try {
      await removeVessel(mmsi);
      toast.success(`Removed vessel ${boatName || mmsi}`);
    } catch (err) {
      toast.error(err.message || "Failed to remove vessel");
    } finally {
      setRemovingMmsi(null);
    }
  };

  const handleSetPrimary = async (mmsi) => {
    setSettingPrimary(mmsi);
    try {
      await setPrimaryVessel(mmsi);
      toast.success("Primary vessel updated");
    } catch (err) {
      toast.error(err.message || "Failed to set primary vessel");
    } finally {
      setSettingPrimary(null);
    }
  };

  return (
    <Card className="glass-panel border-white/10" data-testid="vessel-management">
      <CardHeader>
        <CardTitle className="text-lg text-white flex items-center gap-2">
          <Ship className="w-5 h-5 text-cyan-400" />
          Your Fleet
        </CardTitle>
        <CardDescription className="text-slate-400">
          Manage multiple vessels associated with your account. The primary vessel is used for lock timing calculations.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Current Vessels List */}
        {vessels.length > 0 ? (
          <div className="space-y-2">
            {vessels.map((vessel) => (
              <div 
                key={vessel.mmsi}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  vessel.is_primary 
                    ? "border-cyan-500/50 bg-cyan-500/10" 
                    : "border-slate-700 bg-slate-900/50"
                }`}
                data-testid={`vessel-item-${vessel.mmsi}`}
              >
                <div className="flex items-center gap-3">
                  <Ship className={`w-5 h-5 ${vessel.is_primary ? "text-cyan-400" : "text-slate-500"}`} />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">
                        {vessel.boat_name || "Unnamed Vessel"}
                      </span>
                      {vessel.is_primary && (
                        <Badge variant="outline" className="text-xs border-cyan-500 text-cyan-400">
                          <Star className="w-3 h-3 mr-1" />
                          Primary
                        </Badge>
                      )}
                    </div>
                    <span className="text-sm font-mono text-slate-400">
                      MMSI: {vessel.mmsi}
                    </span>
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  {!vessel.is_primary && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleSetPrimary(vessel.mmsi)}
                      disabled={settingPrimary === vessel.mmsi}
                      className="text-slate-400 hover:text-cyan-400"
                      data-testid={`set-primary-${vessel.mmsi}`}
                    >
                      {settingPrimary === vessel.mmsi ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Star className="w-4 h-4" />
                      )}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemoveVessel(vessel.mmsi, vessel.boat_name)}
                    disabled={removingMmsi === vessel.mmsi}
                    className="text-slate-400 hover:text-red-400"
                    data-testid={`remove-vessel-${vessel.mmsi}`}
                  >
                    {removingMmsi === vessel.mmsi ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4" />
                    )}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-slate-400">
            <Ship className="w-10 h-10 mx-auto mb-2 opacity-50" />
            <p>No vessels in your fleet yet.</p>
            <p className="text-sm">Add your first vessel below.</p>
          </div>
        )}

        {/* Add Vessel Form */}
        <form onSubmit={handleAddVessel} className="pt-4 border-t border-slate-700">
          <Label className="text-slate-300 mb-2 block">Add New Vessel</Label>
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input
                placeholder="MMSI (9 digits)"
                value={newMmsi}
                onChange={(e) => setNewMmsi(e.target.value)}
                className="bg-slate-900/50 border-slate-700 text-white font-mono"
                maxLength={9}
                data-testid="add-vessel-mmsi"
              />
            </div>
            <div className="flex-1">
              <Input
                placeholder="Boat Name (optional)"
                value={newBoatName}
                onChange={(e) => setNewBoatName(e.target.value)}
                className="bg-slate-900/50 border-slate-700 text-white"
                data-testid="add-vessel-name"
              />
            </div>
            <Button
              type="submit"
              disabled={adding || !newMmsi.trim()}
              className="bg-cyan-600 hover:bg-cyan-500 text-white"
              data-testid="add-vessel-btn"
            >
              {adding ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Plus className="w-4 h-4 mr-1" />
                  Add
                </>
              )}
            </Button>
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Your primary vessel is used for lock timing calculations. You can switch the primary vessel at any time.
          </p>
        </form>

        {/* Info Note */}
        <div className="flex items-start gap-2 p-3 rounded-lg bg-blue-500/10 border border-blue-500/20">
          <AlertCircle className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-blue-300">
            Adding a vessel links it to your account. Only one user can claim each MMSI at a time.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
