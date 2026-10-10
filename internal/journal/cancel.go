package journal

import "errors"
// Cancel requests cancellation only while the operation is still in a safe span.
// A later execution engine must check this recorded state before an effect.
func (j *Journal) Cancel(id string)(Record,error){
 j.mu.Lock();defer j.mu.Unlock();r,e:=j.read(id);if e!=nil{return Record{},e}
 if r.State!=Running||!r.Cancellable{return Record{},errors.New("operation cannot be cancelled")}
 r.State=Cancelled;r.Stage="cancelled";r.Cancellable=false
 if e=j.write(r);e!=nil{return Record{},e}
 return r,nil
}
