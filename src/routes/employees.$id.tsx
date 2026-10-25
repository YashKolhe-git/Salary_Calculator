import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ClipboardPen, CreditCard, History, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AppHeader } from "@/components/AppHeader";
import { WorkEntryDialog } from "@/components/WorkEntryDialog";
import { RecordPaymentDialog } from "@/components/RecordPaymentDialog";
import { PaymentHistoryDialog } from "@/components/PaymentHistoryDialog";
import { Field, StatusBadge, bigInput } from "@/components/shared";
import { useAppState } from "@/hooks/useAppState";
import { authService } from "@/services/authService";
import { employeeService } from "@/services/employeeService";
import { workRecordService } from "@/services/workRecordService";
import { toast } from "sonner";
import type { EmployeeBalanceSummary, WorkRecord } from "@/types";
import { formatDate, formatINR, formatWage } from "@/utils/format";

export const Route = createFileRoute("/employees/$id")({
  head: () => ({
    meta: [
      { title: "Work History — Daily Wage Calculator" },
      { name: "description", content: "Daily work history, earnings and pending payments for an employee." },
      { property: "og:title", content: "Work History — Daily Wage Calculator" },
      { property: "og:description", content: "Daily work history, earnings and pending payments for an employee." },
    ],
  }),
  component: LogsPage,
});

function LogsPage() {
  const { id } = Route.useParams();
  const navigate = useNavigate();
  const { state, ready } = useAppState();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [applied, setApplied] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [dialog, setDialog] = useState<{ open: boolean; record?: WorkRecord | undefined }>({ open: false });
  const [payDialog, setPayDialog] = useState<{ open: boolean; record: WorkRecord | null }>({ open: false, record: null });
  const [historyDialog, setHistoryDialog] = useState<{ open: boolean; record: WorkRecord | null }>({ open: false, record: null });
  const [balanceSummary, setBalanceSummary] = useState<EmployeeBalanceSummary | null>(null);
  const [visibleCount, setVisibleCount] = useState(10);

  const loadData = useCallback(() => {
    employeeService.get(id).catch((err) => {
      toast.error(err instanceof Error ? err.message : "Failed to load employee.");
    });
    employeeService.getBalanceSummary(id).then(setBalanceSummary).catch(() => {});
    workRecordService.listForEmployee(id, applied.from, applied.to).catch((err) => {
      toast.error(err instanceof Error ? err.message : "Failed to load work records.");
    });
  }, [id, applied.from, applied.to]);

  useEffect(() => {
    if (!authService.isLoggedIn()) {
      navigate({ to: "/" });
      return;
    }
    loadData();

    const handleUnauthorized = () => {
      navigate({ to: "/" });
      toast.error("Session expired. Please log in again.");
    };
    window.addEventListener("dwc:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("dwc:unauthorized", handleUnauthorized);
  }, [loadData, navigate]);

  // Reset filter and pagination when switching employees
  useEffect(() => {
    setFrom("");
    setTo("");
    setApplied({ from: "", to: "" });
    setVisibleCount(10);
  }, [id]);

  useEffect(() => {
    setVisibleCount(10);
  }, [applied]);

  const employee = state.employees.find((e) => e.id === id) ?? null;
  const records = state.records
    .filter((r) => r.employeeId === id)
    .filter((r) => (!applied.from || r.workDate >= applied.from) && (!applied.to || r.workDate <= applied.to))
    .sort((a, b) => b.workDate.localeCompare(a.workDate));

  // When no date filter is applied, use backend financial summary as the single source of truth
  const isFiltered = Boolean(applied.from || applied.to);
  const totalEarnings = isFiltered
    ? records.reduce((s, r) => s + r.calculatedEarnings, 0)
    : (balanceSummary?.totalEarnings ?? records.reduce((s, r) => s + r.calculatedEarnings, 0));

  const totalPaid = isFiltered
    ? records.reduce((s, r) => s + (r.totalPaid ?? 0), 0)
    : (balanceSummary?.totalPaid ?? records.reduce((s, r) => s + (r.totalPaid ?? 0), 0));

  const outstandingBalance = isFiltered
    ? records.reduce((s, r) => s + (r.balanceDue ?? 0), 0)
    : (balanceSummary?.outstandingBalance ?? records.reduce((s, r) => s + (r.balanceDue ?? 0), 0));

  const daysRecorded = isFiltered ? records.length : (balanceSummary?.workRecordCount ?? records.length);
  const visibleRecords = records.slice(0, visibleCount);
  const hasMore = records.length > visibleCount;

  return (
    <div className="min-h-dvh">
      <AppHeader />
      <main className="mx-auto max-w-5xl space-y-5 px-4 py-5">
        <Button variant="outline" size="xl" asChild>
          <Link to="/dashboard"><ArrowLeft /> Back</Link>
        </Button>

        {ready && !employee && <p className="text-muted-foreground">Employee not found.</p>}

        {ready && employee && (
          <>
            <section>
              <h1 className="break-words text-2xl font-bold">Work History — {employee.name}</h1>
              <p className="text-muted-foreground">
                Assigned wage: <span className="font-semibold text-foreground">{formatWage(employee.wageAmount, employee.wageType)}</span>
                {!employee.isActive && " · Inactive"}
              </p>
            </section>

            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-xl border-2 border-border p-3">
                <p className="text-xs text-muted-foreground sm:text-sm">Days Recorded</p>
                <p className="break-words text-lg font-bold sm:text-xl">{daysRecorded}</p>
              </div>
              <div className="rounded-xl border-2 border-border p-3">
                <p className="text-xs text-muted-foreground sm:text-sm">Total Earnings</p>
                <p className="break-words text-lg font-bold sm:text-xl">{formatINR(totalEarnings)}</p>
              </div>
              <div className="rounded-xl border-2 border-border p-3">
                <p className="text-xs text-muted-foreground sm:text-sm">Total Paid</p>
                <p className="break-words text-lg font-bold text-success sm:text-xl">{formatINR(totalPaid)}</p>
              </div>
              <div className="rounded-xl border-2 border-border p-3">
                <p className="text-xs text-muted-foreground sm:text-sm">Balance Due</p>
                <p className="break-words text-lg font-bold text-warning sm:text-xl">{formatINR(outstandingBalance)}</p>
              </div>
            </div>

            <div className="space-y-3 rounded-xl border-2 border-border p-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Start Date" htmlFor="f-from"><input id="f-from" type="date" className={bigInput} value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
                <Field label="End Date" htmlFor="f-to"><input id="f-to" type="date" className={bigInput} value={to} onChange={(e) => setTo(e.target.value)} /></Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Button size="xl" onClick={() => setApplied({ from, to })}>Apply Filter</Button>
                <Button size="xl" variant="outline" onClick={() => { setFrom(""); setTo(""); setApplied({ from: "", to: "" }); }}>
                  Show All
                </Button>
              </div>
            </div>

            {employee.isActive && (
              <Button size="xl" className="w-full" onClick={() => setDialog({ open: true })}><ClipboardPen /> Record Work</Button>
            )}

            {records.length === 0 ? (
              <div className="rounded-xl border-2 border-dashed border-border p-8 text-center text-muted-foreground space-y-2">
                <p className="font-semibold text-base">No work records yet.</p>
                <p className="text-sm">Work entries for this employee will appear here once recorded.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-xl border-2 border-border bg-card shadow-card">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/60 text-xs font-semibold uppercase text-muted-foreground">
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Work Date</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Regular Earnings</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Extra Pay</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Total Earnings</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Amount Paid</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Outstanding Balance</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap">Payment Status</th>
                        <th scope="col" className="px-4 py-3.5 whitespace-nowrap text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {visibleRecords.map((r) => {
                        const regularEarnings = r.baseAmount !== undefined ? r.baseAmount : (r.calculatedEarnings - (r.extraPay ?? 0));
                        const extraPay = r.extraPay ?? 0;
                        const totalPaidRecord = r.totalPaid ?? 0;
                        const balanceDueRecord = r.balanceDue !== undefined ? r.balanceDue : Math.max(0, r.calculatedEarnings - totalPaidRecord);

                        return (
                          <tr key={r.id} className="hover:bg-muted/30 transition-colors">
                            <td className="px-4 py-3.5 font-semibold text-foreground whitespace-nowrap">
                              {formatDate(r.workDate)}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap font-medium text-foreground">
                              {formatINR(regularEarnings)}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap font-medium text-primary">
                              {extraPay > 0 ? `+${formatINR(extraPay)}` : "—"}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap font-bold text-foreground">
                              {formatINR(r.calculatedEarnings)}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap font-semibold text-success">
                              {formatINR(totalPaidRecord)}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap font-bold text-warning">
                              {formatINR(balanceDueRecord)}
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap">
                              <StatusBadge status={r.paymentStatus} />
                            </td>
                            <td className="px-4 py-3.5 whitespace-nowrap text-right">
                              <div className="flex items-center justify-end gap-1.5">
                                {balanceDueRecord > 0 && (
                                  <Button
                                    size="sm"
                                    className="h-8 px-2.5 text-xs"
                                    onClick={() => setPayDialog({ open: true, record: r })}
                                    title="Record Payment"
                                  >
                                    <CreditCard className="size-3.5" /> Pay
                                  </Button>
                                )}
                                {totalPaidRecord > 0 && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    className="h-8 px-2.5 text-xs"
                                    onClick={() => setHistoryDialog({ open: true, record: r })}
                                    title="Payment History"
                                  >
                                    <History className="size-3.5" /> History
                                  </Button>
                                )}
                                <Button
                                  variant="outline"
                                  size="sm"
                                  className="h-8 px-2.5 text-xs"
                                  onClick={() => setDialog({ open: true, record: r })}
                                  title="Edit Record"
                                >
                                  <Pencil className="size-3.5" /> Edit
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {hasMore && (
                  <div className="flex justify-center pt-2">
                    <Button
                      variant="outline"
                      size="xl"
                      className="w-full sm:w-auto px-8"
                      onClick={() => setVisibleCount((prev) => prev + 10)}
                    >
                      See More ({records.length - visibleCount} remaining)
                    </Button>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </main>

      <WorkEntryDialog
        open={dialog.open}
        onOpenChange={(o) => {
          setDialog((d) => ({ ...d, open: o }));
          if (!o) loadData();
        }}
        employee={employee}
        record={dialog.record}
      />

      <RecordPaymentDialog
        open={payDialog.open}
        onOpenChange={(o) => setPayDialog((p) => ({ ...p, open: o }))}
        record={payDialog.record}
        onSuccess={loadData}
      />

      <PaymentHistoryDialog
        open={historyDialog.open}
        onOpenChange={(o) => setHistoryDialog((h) => ({ ...h, open: o }))}
        record={historyDialog.record}
      />
    </div>
  );
}
