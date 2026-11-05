import {Protected} from '@/components/shell';
import MyBookings from '@/features/operations/my-bookings';
export default function Page(){return <Protected><MyBookings/></Protected>}
