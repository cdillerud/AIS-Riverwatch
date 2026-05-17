import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import {
  Map,
  Plus,
  Trash2,
  Pencil,
  ArrowLeft,
  Calendar,
  Compass,
  Navigation,
  StickyNote,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

const HEADING_OPTIONS = [
  { value: "northbound", label: "Northbound (↑ NB, RM increases)" },
  { value: "southbound", label: "Southbound (↓ SB, RM decreases)" },
];

const emptyTrip = {
  name: "",
  start_rm: "",
  end_rm: "",
  heading: "",
  departure_time: "",
  notes: "",
};

export default function TripsPage() {
  const navigate = useNavigate();
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editing, setEditing] = useState(null); // null | trip object (for edit) | "new"
  const [form, setForm] = useState(emptyTrip);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const fetchTrips = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/trips`, { credentials: "include" });
      if (res.status === 401) {
        navigate("/login");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTrips(data.trips || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [navigate]);

  useEffect(() => {
    fetchTrips();
  }, [fetchTrips]);

  const openNew = () => {
    setForm(emptyTrip);
    setEditing("new");
  };

  const openEdit = (trip) => {
    setForm({
      name: trip.name || "",
      start_rm: trip.start_rm ?? "",
      end_rm: trip.end_rm ?? "",
      heading: trip.heading || "",
      departure_time: trip.departure_time || "",
      notes: trip.notes || "",
    });
    setEditing(trip);
  };

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("Trip name is required");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        start_rm: form.start_rm === "" ? null : Number(form.start_rm),
        end_rm: form.end_rm === "" ? null : Number(form.end_rm),
        heading: form.heading || null,
        departure_time: form.departure_time || null,
        notes: form.notes,
        locks: [],
      };
      const isNew = editing === "new";
      const url = isNew ? `${API}/trips` : `${API}/trips/${editing.trip_id}`;
      const method = isNew ? "POST" : "PUT";
      const res = await fetch(url, {
        method,
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail || `HTTP ${res.status}`);
      }
      toast.success(isNew ? "Trip created" : "Trip updated");
      setEditing(null);
      setForm(emptyTrip);
      await fetchTrips();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      const res = await fetch(`${API}/trips/${confirmDelete.trip_id}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast.success(`Deleted "${confirmDelete.name}"`);
      setConfirmDelete(null);
      await fetchTrips();
    } catch (e) {
      toast.error(e.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-5xl mx-auto p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/dashboard")}
              data-testid="trips-back-btn"
              className="text-slate-300 hover:text-white"
            >
              <ArrowLeft className="w-4 h-4 mr-1" />
              Dashboard
            </Button>
            <h1 className="text-3xl font-bold flex items-center gap-2">
              <Map className="w-7 h-7 text-cyan-400" />
              My Trips
            </h1>
          </div>
          <Button
            onClick={openNew}
            data-testid="trips-new-btn"
            className="bg-cyan-600 hover:bg-cyan-500"
          >
            <Plus className="w-4 h-4 mr-1" />
            New Trip
          </Button>
        </div>

        {/* Body */}
        {loading && (
          <div className="text-center py-12 text-slate-400" data-testid="trips-loading">
            Loading trips…
          </div>
        )}
        {error && (
          <div className="text-center py-12 text-red-400" data-testid="trips-error">
            {error}
          </div>
        )}
        {!loading && !error && trips.length === 0 && (
          <Card className="glass-panel border-slate-800" data-testid="trips-empty">
            <CardContent className="text-center py-16">
              <Map className="w-12 h-12 mx-auto mb-4 text-slate-600" />
              <h2 className="text-xl font-semibold mb-2">No trips saved yet</h2>
              <p className="text-slate-400 mb-6">
                Plan a route between two river miles, save it, and recall it later.
              </p>
              <Button onClick={openNew} className="bg-cyan-600 hover:bg-cyan-500" data-testid="trips-empty-new-btn">
                <Plus className="w-4 h-4 mr-1" />
                Create your first trip
              </Button>
            </CardContent>
          </Card>
        )}

        {!loading && !error && trips.length > 0 && (
          <div className="grid gap-4" data-testid="trips-list">
            {trips.map((t) => (
              <Card key={t.trip_id} className="glass-panel border-slate-800" data-testid={`trip-card-${t.trip_id}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <h3 className="text-lg font-semibold text-white truncate">{t.name}</h3>
                        {t.heading && (
                          <Badge
                            className={
                              t.heading === "northbound"
                                ? "bg-blue-900/40 text-blue-300 border-blue-500"
                                : "bg-orange-900/40 text-orange-300 border-orange-500"
                            }
                          >
                            <Compass className="w-3 h-3 mr-1" />
                            {t.heading === "northbound" ? "↑ NB" : "↓ SB"}
                          </Badge>
                        )}
                      </div>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                        <div>
                          <div className="text-slate-500 text-xs uppercase">Start RM</div>
                          <div className="text-white font-mono">{t.start_rm ?? "—"}</div>
                        </div>
                        <div>
                          <div className="text-slate-500 text-xs uppercase">End RM</div>
                          <div className="text-white font-mono">{t.end_rm ?? "—"}</div>
                        </div>
                        <div>
                          <div className="text-slate-500 text-xs uppercase">Departure</div>
                          <div className="text-white font-mono text-xs">
                            {t.departure_time ? new Date(t.departure_time).toLocaleString() : "—"}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-500 text-xs uppercase">Saved</div>
                          <div className="text-white font-mono text-xs">
                            {t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}
                          </div>
                        </div>
                      </div>
                      {t.notes && (
                        <div className="mt-3 text-sm text-slate-300 bg-slate-900/50 rounded p-2 border border-slate-800">
                          <StickyNote className="w-3 h-3 inline mr-1 text-amber-400" />
                          {t.notes}
                        </div>
                      )}
                    </div>
                    <div className="flex gap-2 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEdit(t)}
                        data-testid={`trip-edit-${t.trip_id}`}
                        className="border-slate-700 text-slate-300 hover:text-white"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => setConfirmDelete(t)}
                        data-testid={`trip-delete-${t.trip_id}`}
                        className="border-red-900/50 text-red-400 hover:bg-red-900/20 hover:text-red-300"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Create / Edit dialog */}
      <Dialog open={editing !== null} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="bg-slate-900 border-slate-800 text-white max-w-lg" data-testid="trips-dialog">
          <DialogHeader>
            <DialogTitle>{editing === "new" ? "New Trip" : "Edit Trip"}</DialogTitle>
            <DialogDescription className="text-slate-400">
              Save a route so you can recall its parameters in Trip Plan.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label htmlFor="trip-name" className="text-slate-300">Name *</Label>
              <Input
                id="trip-name"
                data-testid="trip-form-name"
                placeholder="e.g. Hastings -> Red Wing Saturday"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="bg-slate-950 border-slate-700"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="trip-start" className="text-slate-300">Start RM</Label>
                <Input
                  id="trip-start"
                  data-testid="trip-form-start-rm"
                  type="number"
                  step="0.1"
                  placeholder="820.0"
                  value={form.start_rm}
                  onChange={(e) => setForm({ ...form, start_rm: e.target.value })}
                  className="bg-slate-950 border-slate-700 font-mono"
                />
              </div>
              <div>
                <Label htmlFor="trip-end" className="text-slate-300">End RM</Label>
                <Input
                  id="trip-end"
                  data-testid="trip-form-end-rm"
                  type="number"
                  step="0.1"
                  placeholder="752.8"
                  value={form.end_rm}
                  onChange={(e) => setForm({ ...form, end_rm: e.target.value })}
                  className="bg-slate-950 border-slate-700 font-mono"
                />
              </div>
            </div>
            <div>
              <Label className="text-slate-300">Heading</Label>
              <Select
                value={form.heading}
                onValueChange={(v) => setForm({ ...form, heading: v })}
              >
                <SelectTrigger className="bg-slate-950 border-slate-700" data-testid="trip-form-heading">
                  <SelectValue placeholder="Pick direction" />
                </SelectTrigger>
                <SelectContent className="bg-slate-900 border-slate-700">
                  {HEADING_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="trip-departure" className="text-slate-300">Departure (optional)</Label>
              <Input
                id="trip-departure"
                data-testid="trip-form-departure"
                type="datetime-local"
                value={form.departure_time}
                onChange={(e) => setForm({ ...form, departure_time: e.target.value })}
                className="bg-slate-950 border-slate-700 font-mono"
              />
            </div>
            <div>
              <Label htmlFor="trip-notes" className="text-slate-300">Notes</Label>
              <Textarea
                id="trip-notes"
                data-testid="trip-form-notes"
                placeholder="Crew, fuel, anything to remember…"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="bg-slate-950 border-slate-700 min-h-[80px]"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setEditing(null)}
              disabled={saving}
              data-testid="trip-form-cancel"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving}
              className="bg-cyan-600 hover:bg-cyan-500"
              data-testid="trip-form-save"
            >
              {saving ? "Saving…" : (editing === "new" ? "Create Trip" : "Save Changes")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={confirmDelete !== null} onOpenChange={(o) => { if (!o) setConfirmDelete(null); }}>
        <AlertDialogContent className="bg-slate-900 border-slate-800 text-white" data-testid="trips-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this trip?</AlertDialogTitle>
            <AlertDialogDescription className="text-slate-400">
              "{confirmDelete?.name}" will be permanently removed. This can't be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-slate-800 border-slate-700">Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-600 hover:bg-red-500"
              data-testid="trip-confirm-delete"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
