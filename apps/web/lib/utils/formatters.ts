export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(date);
}

export function formatPercentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export function formatConfidence(confidence: number): string {
  if (confidence >= 0.8) return 'High';
  if (confidence >= 0.6) return 'Medium';
  if (confidence >= 0.4) return 'Low';
  return 'Very Low';
}

export function formatOutcome(outcome: string): string {
  switch (outcome) {
    case 'tenant_favored':
      return 'Tenant Likely to Win';
    case 'landlord_favored':
      return 'Landlord Likely to Win';
    case 'split':
      return 'Likely Split Decision';
    case 'uncertain':
      return 'Outcome Uncertain';
    default:
      return outcome;
  }
}

export function formatIssueType(issue: string): string {
  return issue
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function formatSettlementRange(range: [number, number]): string {
  return `${formatCurrency(range[0])} - ${formatCurrency(range[1])}`;
}
