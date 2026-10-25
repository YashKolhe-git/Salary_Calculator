import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useNavigate } from "@tanstack/react-router";
import { History, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import type { Employee, PaymentStatus, WorkRecord } from "@/types";
import { workRecordService } from "@/services/workRecordService";
import { calculateEarnings, describeCalculation } from "@/utils/wageCalculator";
import { formatINR, formatWage, todayISO, wageTypeLabel } from "@/utils/format";
import { Field, PaymentToggle, RupeeInput, bigDialog, bigInput } from "./shared";

export function WorkEntryDialog({
  open,
  onOpenChange,
  employee,
  record: initialRecord,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  employee: Employee | null;
  record?: WorkRecord | undefined;
}) {
  const navigate = useNavigate();
  const [editing, setEditing] = useState<WorkRecord | undefined>();
  const [date, setDate] = useState(todayISO());
  const [hours, setHours] = useState("");
  const [minutes, setMinutes] = useState("");
  const [rate, setRate] = useState("");
  const [extraPay, setExtraPay] = useState("");
  const [status, setStatus] = useState<PaymentStatus>("not_paid");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Partial<Record<"date" | "hours" | "minutes" | "rate" | "extraPay", string>>>({});
  const [duplicate, setDuplicate] = useState<WorkRecord | null>(null);
  const [saving, setSaving] = useState(false);

  function loadRecord(r?: WorkRecord) {
    setEditing(r);
    setDuplicate(null);
    setErrors({});
    setDate(r?.workDate ?? todayISO());
    setHours(r ? String(r.hoursWorked) : "");
    setMinutes(r ? String(r.minutesWorked) : "");
    setNotes(r?.notes ?? "");

    const currentWageType = r?.wageType ?? employee?.wageType ?? "hourly";
    let initialRate = "";
    if (r) {
      if (currentWageType === "monthly" || currentWageType === "daily") {
        initialRate = r.baseAmount !== undefined ? String(r.baseAmount) : String(r.calculatedEarnings - (r.extraPay ?? 0));
      } else {
        initialRate = String(r.wageRateUsed);
      }
    } else {
      if (currentWageType === "monthly") {
        initialRate = ""; // Monthly requires entering the actual regular earnings manually
      } else if (currentWageType === "daily") {
        initialRate = employee?.wageAmount ? String(employee.wageAmount) : "";
      } else {
        initialRate = String(employee?.wageAmount ?? 0);
      }
    }
    setRate(initialRate);

    setExtraPay(r?.extraPay ? String(r.extraPay) : "");
    setStatus(r?.paymentStatus ?? "not_paid");
  }

  useEffect(() => {
    if (open) loadRecord(initialRecord);
  }, [open, initialRecord, employee?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const wageType = editing?.wageType ?? employee?.wageType ?? "hourly";
  const regularEarnings = useMemo(
    () => calculateEarnings({ wageType, rate: Number(rate) || 0, hours: Number(hours) || 0, minutes: Number(minutes) || 0 }),
    [wageType, rate, hours, minutes],
  );
  const totalEarnings = regularEarnings + (Number(extraPay) || 0);

  if (!employee) return null;

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!employee) return;
    if (!editing && !employee.isActive) {
      toast.error(`Employee '${employee.name}' is inactive. Cannot create new work records.`);
      return;
    }
    const errs: Partial<Record<"date" | "hours" | "minutes" | "rate" | "extraPay", string>> = {};
    const h = Number(hours || 0);
    const m = Number(minutes || 0);
    const extra = Number(extraPay || 0);

    if (!date) errs.date = "Please choose a date.";

    if (wageType === "hourly") {
      if (!Number.isInteger(h) || h < 0 || h > 24) errs.hours = "Hours must be a whole number between 0 and 24.";
      if (!Number.isInteger(m) || m < 0 || m > 59) errs.minutes = "Minutes must be between 0 and 59.";
      if (h === 0 && m === 0) errs.hours = "Please enter the time worked.";
      if (rate === "" || isNaN(Number(rate)) || Number(rate) < 0) errs.rate = "Wage rate must be 0 or more.";
    } else if (wageType === "daily") {
      if (rate === "" || isNaN(Number(rate)) || Number(rate) < 0) {
        errs.rate = "Please enter the regular earnings.";
      }
    } else if (wageType === "monthly") {
      if (rate === "" || isNaN(Number(rate)) || Number(rate) < 0) {
        errs.rate = "Please enter the manually agreed regular earnings.";
      }
    }

    if (isNaN(extra) || extra < 0) errs.extraPay = "Extra pay cannot be negative.";

    setErrors(errs);
    if (Object.keys(errs).length) return;

    const input = {
      employeeId: employee.id,
      workDate: date,
      hoursWorked: wageType === "hourly" ? h : (editing?.hoursWorked ?? 0),
      minutesWorked: wageType === "hourly" ? m : (editing?.minutesWorked ?? 0),
      wageType,
      wageRateUsed: wageType === "monthly" ? (employee.wageAmount || Number(rate)) : Number(rate),
      baseAmount: regularEarnings,
      extraPay: extra,
      paymentStatus: status,
      notes: notes.trim() || undefined,
    };

    setSaving(true);
    try {
      if (editing) {
        await workRecordService.update(editing.id, input);
        toast.success("Work record updated.");
      } else {
        await workRecordService.create(input);
        toast.success(`Work saved for ${employee.name}.`);
      }
      onOpenChange(false);
    } catch (err) {
      if ((err as Error).message === "DUPLICATE") {
        const dup = await workRecordService.findByDate(employee.id, date);
        setDuplicate(dup ?? workRecordService.findByDateSync(employee.id, date) ?? null);
      } else {
        toast.error(err instanceof Error ? err.message : "Failed to save work record.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={bigDialog}>
        <DialogHeader className="text-left">
          <DialogTitle className="text-xl">{editing ? "Edit Work Record" : "Record Daily Work"}</DialogTitle>
          <DialogDescription className="break-words text-lg font-semibold text-foreground">{employee.name}</DialogDescription>
        </DialogHeader>

        {duplicate ? (
          <div className="space-y-4">
            <div className="rounded-lg border-2 border-warning/40 bg-warning-soft p-4 text-base text-foreground">
              Work has already been recorded for this employee on this date. Would you like to edit the existing entry?
            </div>
            <div className="flex flex-col-reverse gap-3 sm:flex-row">
              <Button variant="outline" size="xl" className="w-full sm:flex-1" onClick={() => setDuplicate(null)}>Go Back</Button>
              <Button size="xl" className="w-full sm:flex-1" onClick={() => loadRecord(duplicate)}>Edit Existing Entry</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={save} className="space-y-4" noValidate>
            <Field label="Work Date" htmlFor="we-date" error={errors.date}>
              <input id="we-date" type="date" max={todayISO()} className={bigInput} value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>

            {wageType === "hourly" ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Wage Type">
                    <input className={bigInput} value={wageTypeLabel[wageType]} disabled />
                  </Field>
                  <Field
                    label="Hourly Rate"
                    htmlFor="we-rate"
                    error={errors.rate}
                    hint={employee.wageAmount ? `Ref: ${formatWage(employee.wageAmount, "hourly")}` : undefined}
                  >
                    <RupeeInput id="we-rate" value={rate} onChange={(e) => setRate(e.target.value)} />
                  </Field>
                </div>
                <p className="-mt-2 text-sm text-muted-foreground">
                  You can change the rate for this day only.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Hours Worked" htmlFor="we-h" error={errors.hours}>
                    <input id="we-h" type="number" inputMode="numeric" min={0} max={24} placeholder="0" className={bigInput} value={hours} onChange={(e) => setHours(e.target.value)} />
                  </Field>
                  <Field label="Minutes Worked" htmlFor="we-m" error={errors.minutes}>
                    <input id="we-m" type="number" inputMode="numeric" min={0} max={59} placeholder="0" className={bigInput} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
                  </Field>
                </div>
              </>
            ) : wageType === "daily" ? (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Wage Type">
                    <input className={bigInput} value={wageTypeLabel[wageType]} disabled />
                  </Field>
                  <Field
                    label="Regular Earnings"
                    htmlFor="we-rate"
                    error={errors.rate}
                    hint={employee.wageAmount ? `Daily ref: ${formatWage(employee.wageAmount, "daily")}` : undefined}
                  >
                    <RupeeInput id="we-rate" value={rate} onChange={(e) => setRate(e.target.value)} />
                  </Field>
                </div>
                <p className="-mt-2 text-sm text-muted-foreground">
                  Regular earnings are manually entered and not calculated from hours.
                </p>
              </>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Wage Type">
                    <input className={bigInput} value={wageTypeLabel[wageType]} disabled />
                  </Field>
                  <Field
                    label="Regular Earnings"
                    htmlFor="we-rate"
                    error={errors.rate}
                    hint={employee.wageAmount ? `Monthly ref: ${formatWage(employee.wageAmount, "monthly")}` : undefined}
                  >
                    <RupeeInput id="we-rate" value={rate} onChange={(e) => setRate(e.target.value)} />
                  </Field>
                </div>
                <p className="-mt-2 text-sm text-muted-foreground">
                  Monthly earnings are manually entered and never calculated by dividing by 30 or hours.
                </p>
              </>
            )}

            <Field label="Extra Pay / Incentive (Optional)" htmlFor="we-extra" error={errors.extraPay}>
              <RupeeInput
                id="we-extra"
                placeholder="0.00"
                value={extraPay}
                onChange={(e) => setExtraPay(e.target.value)}
              />
            </Field>

            <Field label="Notes / Reference (Optional)" htmlFor="we-notes">
              <input
                id="we-notes"
                type="text"
                className={bigInput}
                placeholder="Optional remarks"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>

            <div className="rounded-lg border-2 border-primary/30 bg-accent p-4">
              <div className="flex items-baseline justify-between">
                <p className="text-sm text-muted-foreground">Total Daily Earnings</p>
                {Number(extraPay) > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Regular: {formatINR(regularEarnings)} + Extra: {formatINR(Number(extraPay))}
                  </p>
                )}
              </div>
              <p className="text-3xl font-bold text-foreground">{formatINR(totalEarnings)}</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {describeCalculation(wageType)} ·{" "}
                {wageType === "monthly"
                  ? `Monthly ref: ${formatWage(employee.wageAmount, "monthly")}`
                  : wageType === "daily"
                  ? `Daily ref: ${formatWage(employee.wageAmount, "daily")}`
                  : formatWage(Number(rate) || 0, "hourly")}
              </p>
            </div>

            <Field label="Payment Status">
              <PaymentToggle value={status} onChange={setStatus} />
            </Field>

            <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row">
              <Button type="button" variant="outline" size="xl" className="w-full sm:flex-1" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button type="submit" size="xl" className="w-full sm:flex-1" disabled={saving}>
                {saving && <Loader2 className="animate-spin" />} Save Work
              </Button>
            </div>
            <Button
              type="button"
              variant="outline"
              size="xl"
              className="w-full"
              onClick={() => {
                onOpenChange(false);
                navigate({ to: "/employees/$id", params: { id: employee.id } });
              }}
            >
              <History /> View Logs
            </Button>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
